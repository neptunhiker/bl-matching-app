import logging

from django.conf import settings
from django.urls import reverse
from slack_sdk import WebClient
from django.utils import timezone

from accounts.models import User
from matching.locks import _get_locked_request_to_coach
from matching.models import RequestToCoach
from matching.tokens import generate_coach_action_tokens
from slack.models import SlackLog



logger = logging.getLogger(__name__)

def send_first_coach_request_slack(rtc: RequestToCoach, triggered_by: str="system", triggered_by_user: User = None):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = rtc.coach
    participant = rtc.matching_attempt.participant
    url_participant = settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk})
    user_id = coach.slack_user_id
    start_date = rtc.matching_attempt.participant.start_date
    
    if not user_id:
        raise ValueError(f"Coach {rtc.coach} does not have a Slack user ID")
    
    # Open a DM channel
    response = client.conversations_open(users=[user_id])
    dm_channel = response["channel"]["id"]
    
    rtc = _get_locked_request_to_coach(rtc)
    rtc = rtc.send_request(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    coach = rtc.coach
    
    accept_url, decline_url = generate_coach_action_tokens(rtc)
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "✨ Neue Coaching-Anfrage"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Gute Neuigkeiten, {coach.first_name}! Hättest du Lust, dieses Coaching zu übernehmen?\n\n"
                    f"*Teilnehmer:in:* {participant}\n"
                    f"*Unterrichtseinheiten:* {rtc.ue}\n"
                    f"*Startdatum:* {start_date.strftime('%d.%m.%Y')}\n\n"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    # format deadline safely in case it's None and show it in local time
                    (
                        f"Bitte gib uns kurz bis zum *{timezone.localtime(rtc.deadline_at).strftime('%d.%m.%Y – %H:%M')} Uhr* Bescheid. Ein Klick genügt 👇"
                    )
                    
                )
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Ja, ich übernehme das Coaching!"
                },
                "url": accept_url,
                "style": "primary"
                },
                {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "🙂 Diesmal passt es leider nicht"
                },
                "url": decline_url,
                "style": "danger"
                },
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Mehr Infos zum Coaching mit *{rtc.matching_attempt.participant.first_name}* "
                    f"findest du hier → <{url_participant}|Coaching ansehen>"
                )
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Wenn du annimmst, verbinden wir dich direkt mit "
                        f"*{rtc.matching_attempt.participant.first_name}* für ein Kennenlerngespräch. "
                        "So könnt ihr euch vor dem Start kurz austauschen."
                    )
                }
            ]
        }
    ]

    subject = f"Matching-Anfrage für {rtc.matching_attempt.participant}"


    
    # Send the message
    client.chat_postMessage(
        channel=dm_channel,
        text=subject,
        blocks=blocks
    )
    
    # turnblocks into a string for logging
    message = "\n".join([block["text"]["text"] for block in blocks if "text" in block and "text" in block["text"]])
    
    # Log the message in the database
    SlackLog.objects.create(
        to=coach,
        subject=subject,
        message=message,
        status=SlackLog.Status.SENT,
        slack_trigger=SlackLog.SlackTrigger.AUTOMATED,
        request_to_coach=rtc,
        sent_by=triggered_by,
        sent_by_user=triggered_by_user,
    )
    