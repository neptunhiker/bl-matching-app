import logging

from django.conf import settings
from django.urls import reverse
from slack_sdk import WebClient
from django.utils import timezone

from accounts.models import User
from matching.locks import _get_locked_request_to_coach, _get_locked_matching_attempt
from matching.models import RequestToCoach, MatchingAttempt
from matching.tokens import generate_accept_and_decline_token, generate_intro_call_feedback_url
from matching.utils import get_urgency_message
from slack.models import SlackLog



logger = logging.getLogger(__name__)

def send_first_coach_request_slack(rtc: RequestToCoach, triggered_by: str="system", triggered_by_user: User = None):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = rtc.coach
    participant = rtc.matching_attempt.participant
    url_participant = settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk})
    user_id = coach.slack_user_id
    start_date = rtc.matching_attempt.participant.start_date
    ue = rtc.ue
    deadline_at = rtc.deadline_at
    
    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")
    
    # Open a DM channel
    response = client.conversations_open(users=[user_id])
    dm_channel = response["channel"]["id"]
    
    rtc = _get_locked_request_to_coach(rtc)
    rtc = rtc.send_request(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    accept_url, decline_url = generate_accept_and_decline_token(rtc)
    
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
                    f"*Unterrichtseinheiten:* {ue}\n"
                    f"*Startdatum:* {start_date.strftime('%d.%m.%Y')}\n\n"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    (
                        f"Bitte gib uns bis zum *{timezone.localtime(deadline_at).strftime('%d.%m.%Y – %H:%M')} Uhr* Bescheid.\n" 
                        f"Ein Klick genügt 👇"
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
                    f"Mehr Infos zum Coaching mit *{participant.first_name}* "
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
                        f"*{participant.first_name}* für ein Kennenlerngespräch. "
                        "So könnt ihr euch vor dem Start kurz austauschen."
                    )
                }
            ]
        }
    ]

    subject = f"Matching-Anfrage für {participant.first_name}"


    
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
    
    

def send_reminder_coach_request_slack(rtc: RequestToCoach, triggered_by: str="system", triggered_by_user: User = None):
  
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
    rtc = rtc.send_reminder(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    coach = rtc.coach
    
    accept_url, decline_url = generate_accept_and_decline_token(rtc)
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":Bell: Erinnerung: Coaching-Anfrage"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Bitte antworte uns, ob du das Coaching übernehmen möchtest.\n\n"
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
                    (
                        f"Du hast noch bis zum *{timezone.localtime(rtc.deadline_at).strftime('%d.%m.%Y – %H:%M')} Uhr* Zeit. Ansonsten müssen wir leider einen anderen Coach fragen.\n" "Ein Klick genügt 👇"
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
    
def send_intro_call_request_slack(matching_attempt: MatchingAttempt, triggered_by: str="system", triggered_by_user: User = None):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    url_participant = settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk})
    

    user_id = coach.slack_user_id
    start_date = participant.start_date
    
    urgency_msg = get_urgency_message(participant, start_date=start_date)
    
    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")
    
    # Open a DM channel
    response = client.conversations_open(users=[user_id])
    dm_channel = response["channel"]["id"]
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    matching_attempt = matching_attempt.send_intro_call_request(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    intro_call_feedback_url = generate_intro_call_feedback_url(matching_attempt)
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📅 Nächster Schritt: Intro-Call mit {participant}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Vielen Dank nochmal, dass du das Coaching mit *{participant.first_name}* übernehmen möchtest! 🙌\n\n"
                    f"Jetzt fehlt nur noch ein kurzer Schritt, bevor es losgehen kann."
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*1️⃣ Bitte melde dich bei {participant.first_name}*\n"
                    f"Schreib kurz eine Nachricht, um ein *Kennenlerngespräch* zu vereinbaren.\n\n"
                    f"📧 `{participant.email}`\n\n"
                    f"*{participant.first_name}* weiß bereits Bescheid und wartet auf deine Nachricht 🙂"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*2️⃣ Führt ein kurzes Kennenlerngespräch*\n"
                    f"Dabei könnt ihr euch austauschen und kurz über die Coaching-Ziele sprechen."
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*3️⃣ Danach bestätigst du den Coaching-Start*\n"
                    f"Sobald ihr gesprochen habt, bitten wir dich nur noch, den Coaching-Start zu bestätigen. Das kannst du mit nur einem Klick <{intro_call_feedback_url}|hier> tun. Danach kann es auch schon losgehen! 🚀"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🔎 *Alle Infos zum Coaching*\n"
                    f"Hier findest du nochmal die wichtigsten Details zu *{participant.first_name}* "
                    f"und den Coaching-Zielen:\n"
                    f"<{url_participant}|➡ Coaching ansehen>"
                )
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"⚠️ *Wichtig:* {urgency_msg}"
                    )
                }
            ]
        }
    ]

    subject = f"Intro-Call ansetzen mit {participant.first_name}"
    
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
        matching_attempt=matching_attempt,
        sent_by=triggered_by,
        sent_by_user=triggered_by_user,
    )
    
def send_coaching_starting_info_slack(matching_attempt: MatchingAttempt, triggered_by: str="system", triggered_by_user: User = None):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    url_participant = settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk})

    user_id = coach.slack_user_id
    start_date = participant.start_date
    
    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")
    
    # Open a DM channel
    response = client.conversations_open(users=[user_id])
    dm_channel = response["channel"]["id"]
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    matching_attempt = matching_attempt.send_coaching_start_info(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":star-struck: Nächster Schritt: Coaching-Start mit {participant}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Es kann losgehen! Dein Coaching mit *{participant.first_name}* startet jetzt offiziell. 🙌\n\n"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Bitte organisiere nun die ersten Coaching-Sessions mit {participant.first_name}.* Am besten wäre es, wenn der erste Termin gleich am {start_date.strftime('%d.%m.%Y')} stattfindet.\n"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Falls du noch Fragen hast oder Unterstützung brauchst, melde dich gerne jederzeit bei uns im Team! Wir sind hier, um dich zu unterstützen. 😊"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🔎 *Alle Infos zum Coaching*\n"
                    f"Hier findest du nochmal die wichtigsten Details zu *{participant.first_name}* "
                    f"und den Coaching-Zielen:\n"
                    f"<{url_participant}|➡ Coaching ansehen>"
                )
            },
        },
    ]

    subject = f":star-struck: Coaching mit {participant.first_name} kann starten"
    
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
        matching_attempt=matching_attempt,
        sent_by=triggered_by,
        sent_by_user=triggered_by_user,
    )