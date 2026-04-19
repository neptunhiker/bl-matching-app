import logging

from django.conf import settings
from django.urls import reverse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from django.utils import timezone

from accounts.models import User
from matching.locks import _get_locked_request_to_coach, _get_locked_matching_attempt

from matching.tokens import generate_accept_and_decline_token, generate_intro_call_feedback_url
from matching.utils import get_urgency_message, get_standard_extension_deadline
from slack.models import SlackLog



logger = logging.getLogger(__name__)

def create_slack_log(to: User, subject: str, message: str, request_to_coach=None, matching_attempt=None, sent_by=SlackLog.SentBy.SYSTEM, status=SlackLog.Status.SENT, error_message=""):

    # Only request_to_coach or matching_attempt can be set, not both
    if request_to_coach and matching_attempt:
        raise ValueError("Only request_to_coach or matching_attempt can be set, not both.")

    if not request_to_coach and not matching_attempt:
        raise ValueError("Either request_to_coach or matching_attempt must be set.")

    if request_to_coach:
        slack_log = SlackLog.objects.create(
            to=to,
            subject=subject,
            message=message,
            request_to_coach=request_to_coach,
            sent_by=sent_by,
            status=status,
            error_message=error_message,
        )
    else:
        slack_log = SlackLog.objects.create(
            to=to,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=sent_by,
            status=status,
            error_message=error_message,
        )

    return slack_log


def _open_dm_channel(client: WebClient, user_id: str) -> str:
    """Open a Slack DM channel with a user and return the channel ID."""
    response = client.conversations_open(users=[user_id])
    return response["channel"]["id"]


def _blocks_to_text(blocks: list) -> str:
    """Convert Slack blocks to a plain-text string for logging.

    Handles section blocks (block["text"]["text"]) and context blocks
    (block["elements"][n]["text"]) so context elements are not silently dropped.
    """
    parts = []
    for block in blocks:
        if "text" in block and isinstance(block["text"], dict) and "text" in block["text"]:
            parts.append(block["text"]["text"])
        elif block.get("type") == "context":
            for element in block.get("elements", []):
                if isinstance(element, dict) and "text" in element:
                    parts.append(element["text"])
    return "\n".join(parts)


def send_first_coach_request_slack(rtc):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = rtc.coach
    participant = rtc.matching_attempt.participant
    user_id = coach.slack_user_id
    start_date = rtc.matching_attempt.participant.start_date
    ue = rtc.ue
    deadline_at = rtc.deadline_at
    
    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")

    rtc = _get_locked_request_to_coach(rtc)
    accept_url, decline_url = generate_accept_and_decline_token(rtc)

    logger.info(f"Sending first coach request Slack to coach {coach} (rtc: {rtc.id})")
    subject = f"Matching-Anfrage für {participant.first_name}"

    info_blocks = []
    if participant.coaching_target:
        info_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Coaching-Ziel*\n{participant.coaching_target}"
            }
        })
    if participant.background_information:
        info_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Hintergrundinformationen*\n{participant.background_information}"
            }
        })

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
                    f"*Coaching mit:* {participant}\n"
                    f"*Unterrichtseinheiten:* {ue}\n"
                    f"*Startdatum:* {start_date.strftime('%d.%m.%Y')}\n\n"
                )
            }
        },
        *info_blocks,
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Bitte gib uns bis zum *{timezone.localtime(deadline_at).strftime('%d.%m.%Y – %H:%M')} Uhr* Bescheid.\n"
                    f"Ein Klick genügt 👇"
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
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Wenn du annimmst, geben wir dir die Kontaktdaten von "
                        f"*{participant.first_name}*, damit du ein  Kennenlerngespräch vereinbaren kannst. "
                        "So könnt ihr euch vor dem Start kurz austauschen."
                    )
                }
            ]
        }
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent first coach request Slack to coach {coach}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message=message,
            request_to_coach=rtc,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending first coach request to {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            request_to_coach=rtc,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error sending first coach request to {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            request_to_coach=rtc,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )

    

def send_reminder_coach_request_slack(rtc):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = rtc.coach
    participant = rtc.matching_attempt.participant
    user_id = coach.slack_user_id
    start_date = rtc.matching_attempt.participant.start_date
    
    rtc = _get_locked_request_to_coach(rtc)  # acquire lock first
    coach = rtc.coach
    user_id = coach.slack_user_id

    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")

    accept_url, decline_url = generate_accept_and_decline_token(rtc)

    logger.info(f"Sending reminder coach request Slack to coach {coach} (rtc: {rtc.id})")
    subject = f"Erinnerung - Matching-Anfrage für {rtc.matching_attempt.participant.first_name}"

    info_blocks = []
    if participant.coaching_target:
        info_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Coaching-Ziel*\n{participant.coaching_target}"
            }
        })
    if participant.background_information:
        info_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Hintergrundinformationen*\n{participant.background_information}"
            }
        })

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
        *info_blocks,
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Du hast noch bis zum *{timezone.localtime(rtc.deadline_at).strftime('%d.%m.%Y – %H:%M')} Uhr* Zeit. Ansonsten müssen wir leider einen anderen Coach fragen.\n"
                    "Ein Klick genügt 👇"
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
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Wenn du annimmst, geben wir dir die Kontaktdaten von "
                        f"*{participant.first_name}*, damit du ein  Kennenlerngespräch vereinbaren kannst. "
                        "So könnt ihr euch vor dem Start kurz austauschen."
                    )
                }
            ]
        }
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent reminder coach request Slack to coach {coach}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message=message,
            request_to_coach=rtc,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending reminder to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            request_to_coach=rtc,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error sending reminder to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            request_to_coach=rtc,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    
def send_intro_call_request_slack(matching_attempt):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    

    user_id = coach.slack_user_id
    start_date = participant.start_date
    
    urgency_msg = get_urgency_message(participant, start_date=start_date)
    
    deadline_for_intro_call = matching_attempt.intro_call_deadline_at
    
    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")

    intro_call_feedback_url = generate_intro_call_feedback_url(matching_attempt)

    logger.info(f"Sending intro call request Slack to coach {coach} (matching_attempt: {matching_attempt.id})")
    subject = f"Vereinbare ein Kennenlerngespräch mit {participant.first_name}"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📅 Bitte vereinbare ein Kennenlerngespräch mit {participant}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🙌 Vielen Dank nochmal, dass du das Coaching mit *{participant.first_name}* übernehmen möchtest! Jetzt fehlt nicht mehr viel, bevor es losgehen kann."
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*① Bitte vereinbare ein Kennenlerngespräch mit {participant.first_name} bis zum {deadline_for_intro_call.strftime('%d.%m.%Y')} um {deadline_for_intro_call.strftime('%H:%M')} Uhr*\n"
                    f"*{participant.first_name}* weiß bereits Bescheid und wartet darauf, von Dir zu hören 🙂.\n"
                    f"📧 `{participant.email}`"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*② Führt ein kurzes Kennenlerngespräch*\n"
                    f"Dabei kannst du *{participant.first_name}* (besser) kennenlernen und über die Coaching-Ziele sprechen."
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*③ Danach bestätigst du den Coaching-Start*\n"
                    f"*Nach* dem Kennenlerngespräch bestätige uns bitte, dass ihr gesprochen habt und dass es aus deiner Sicht losgehen kann. Wichtig: Bitte erst bestätigen nachdem ihr gesprochen habt, denn wir informieren {participant.first_name} *sofort* nach deiner Bestätigung."
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
                    "text": "🚀 Kennenlerngespräch hat stattgefunden!"
                },
                "url": intro_call_feedback_url,
                "style": "primary"
                },
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*④ Nachdem wir die Bestätigung von Dir erhalten haben, fragen wir auch bei {participant.first_name}* nach, ob alles in Ordnung ist und das Coaching starten kann. Sobald wir grünes Licht haben, geht es offiziell los! 🎉"
                )
            }
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

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent intro call request Slack to coach {coach}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending intro call request to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error sending intro call request to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    
def send_coaching_starting_info_slack(matching_attempt):
  
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant

    user_id = coach.slack_user_id
    start_date = participant.start_date
    
    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")

    logger.info(f"Sending coaching starting info Slack to coach {coach} (matching_attempt: {matching_attempt.id})")
    subject = f"🤩 Coaching mit {participant.first_name} kann starten"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🤩 Coaching mit {participant.first_name} bitte starten"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Es kann losgehen! Wir haben auch von {participant.first_name} eine positive Rückmeldung zu eurem Kennenlerngespräch erhalten. Dein Coaching mit *{participant.first_name}* startet jetzt also offiziell. 🙌\n\n"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Bitte organisiere nun die ersten Coaching-Sessions.* Am besten wäre es, wenn der erste Termin gleich am {start_date.strftime('%d.%m.%Y')} stattfindet.\n"
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
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent coaching starting info Slack to coach {coach}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending coaching starting info to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error sending coaching starting info to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    
def send_escalation_info_slack(matching_attempt):
    """Send a Slack message to the BL contact when the participant has indicated that there are still open questions after the intro call and an escalation is needed."""
    client = WebClient(token=settings.SLACK_BOT_TOKEN)

    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    bl_contact = matching_attempt.bl_contact

    url_participant = settings.SITE_URL.rstrip("/") + reverse(
        "participant_detail", kwargs={"pk": participant.pk}
    )

    user_id = bl_contact.slack_user_id

    if not user_id:
        raise ValueError(f"BL contact {bl_contact} does not have a Slack user ID")

    logger.info(f"Sending escalation info Slack to BL contact {bl_contact} (matching_attempt: {matching_attempt.id})")
    subject = f"⚠️ Klärungsbedarf bei {participant.first_name}"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⚠️ {participant} benötigt Klärung"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{participant.first_name}* hat sich nach dem Kennenlerngespräch "
                    f"mit *{coach}* gegen einen direkten Coaching-Start entschieden und stattdessen "
                    f"*Klärungsbedarf angemeldet.*"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"👉 *Bitte kontaktiere {participant.first_name} proaktiv so schnell wie möglich*, "
                    "um die offenen Fragen zu klären."
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🔎 *Teilnehmerdetails*\n\n"
                    f"<{url_participant}|➡ Zum Profil von {participant.first_name}>"
                )
            },
        },
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent escalation info Slack to BL contact {bl_contact}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending escalation info to BL contact {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error sending escalation info to BL contact {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    
def send_all_rtcs_declined_info_slack(matching_attempt):
    """Send a Slack message to the BL contact when all RTCs have been declined and the matching attempt has failed."""
    client = WebClient(token=settings.SLACK_BOT_TOKEN)

    participant = matching_attempt.participant
    bl_contact = matching_attempt.bl_contact

    url_participant = settings.SITE_URL.rstrip("/") + reverse(
        "participant_detail", kwargs={"pk": participant.pk}
    )
    url_matching_attempt = settings.SITE_URL.rstrip("/") + reverse(
        "matching_attempt_detail", kwargs={"pk": matching_attempt.pk}
    )

    user_id = bl_contact.slack_user_id

    if not user_id:
        raise ValueError(f"BL contact {bl_contact} does not have a Slack user ID")

    logger.info(f"Sending all-RTCs-declined Slack to BL contact {bl_contact} (matching_attempt: {matching_attempt.id})")
    subject = f"⚠️ Alle Matching-Anfragen für ein Coaching mit {participant.first_name} abgelehnt oder abgelaufen"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⚠️ Alle Matching-Anfragen für ein Coaching mit {participant.first_name} abgelehnt oder abgelaufen"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Alle angefragten Coaches haben ein Coaching mit *{participant.first_name}* abgelehnt oder die Anfragen sind abgelaufen. "
                    f"Das Matching ist damit (vorerst) gescheitert."
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"👉 Bitte schau Dir schnellstmöglich das <{url_matching_attempt}|➡ Matching> an und nimm Kontakt mit {participant.first_name} auf."
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🔎 *Teilnehmerdetails*\n\n"
                    f"<{url_participant}|➡ Zum Profil von {participant.first_name}>"
                )
            },
        },
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent all-RTCs-declined Slack to BL contact {bl_contact}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending all-RTCs-declined info to BL contact {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error sending all-RTCs-declined info to BL contact {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    
def send_intro_call_reminder_slack(matching_attempt):
    """Send a reminder Slack message to the coach asking them to organise the intro call before the extended deadline."""
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    url_participant = settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk})
    deadline = matching_attempt.intro_call_deadline_at
    user_id = coach.slack_user_id

    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")

    intro_call_feedback_url = generate_intro_call_feedback_url(matching_attempt)

    logger.info(f"Sending intro call reminder Slack to coach {coach} (matching_attempt: {matching_attempt.id})")
    subject = f"Erinnerung: Bitte vereinbare ein Kennenlerngespräch mit {participant.first_name}"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔔 Erinnerung: Kennenlerngespräch mit {participant}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Wir wollten dich kurz erinnern, dass du uns noch keine Rückmeldung zu deinem Kennenlerngespräch mit "
                    f"*{participant.first_name}* gegeben hast.\n\n"
                    f"Bitte melde dich bis spätestens *{timezone.localtime(deadline).strftime('%d.%m.%Y – %H:%M')} Uhr* bei uns und bestätige bitte, dass ihr gesprochen habt und dass es aus deiner Sicht losgehen kann."
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
                        "text": "🚀 Kennenlerngespräch hat stattgefunden!"
                    },
                    "url": intro_call_feedback_url,
                    "style": "primary"
                },
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{url_participant}|➡ Zum Profil von {participant.first_name}>"
            },
        },
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent intro call reminder Slack to coach {coach}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending intro call reminder to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error sending intro call reminder to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )


def send_intro_call_timeout_notification_to_staff_slack(matching_attempt):
    """Notify the BL staff contact via Slack that the coach has not organised the intro call even after the reminder. Staff should escalate manually."""
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    bl_contact = matching_attempt.bl_contact
    url_participant = settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk})
    deadline = matching_attempt.intro_call_deadline_at
    user_id = bl_contact.slack_user_id if bl_contact else None

    if not user_id:
        raise ValueError(f"BL contact for matching attempt {matching_attempt.id} does not have a Slack user ID")

    logger.info(f"Sending intro call timeout staff notification Slack to BL contact {bl_contact} (matching_attempt: {matching_attempt.id})")
    subject = f"⚠️ Coach hat kein Kennenlerngespräch mit {participant.first_name} vereinbart"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⚠️ Kein Kennenlerngespräch vereinbart – bitte eskalieren"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{coach}* hat uns trotz Erinnerung bisher keine Rückmeldung zu einem Kennenlerngespräch mit *{participant.first_name}* gegeben.\n\n"
                    f"Bitte kontaktiere *{coach.first_name}* direkt und kläre, ob das Coaching noch stattfinden kann."
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Teilnehmer:in:* {participant}\n"
                    f"*Coach:* {coach}\n\n"
                )
            },
        },
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent intro call timeout staff notification Slack to {bl_contact}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending intro call timeout notification to staff {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending intro call timeout notification to staff {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )


def send_clarification_call_booked_info_to_staff_slack(matching_attempt):
    """Notify BL contact when a participant books a clarification (Check In) call via Calendly."""
    client = WebClient(token=settings.SLACK_BOT_TOKEN)

    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    bl_contact = matching_attempt.bl_contact

    url_participant = settings.SITE_URL.rstrip("/") + reverse(
        "participant_detail", kwargs={"pk": participant.pk}
    )

    user_id = bl_contact.slack_user_id
    if not user_id:
        raise ValueError(f"BL contact {bl_contact} does not have a Slack user ID")

    booking = (
        matching_attempt.clarification_call_bookings
        .filter(status="active")
        .order_by("-created_at")
        .first()
    )

    subject = f"📅 {participant.first_name} hat ein Klärungsgespräch gebucht"

    # Build start-time block content
    if booking and booking.start_time:
        local_time = timezone.localtime(booking.start_time)
        time_str = local_time.strftime("%d.%m.%Y, %H:%M Uhr")
        booking_info = f"📆 *Termin:* {time_str}"
    else:
        booking_info = "📆 *Termin:* (nicht verfügbar)"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📅 {participant} hat ein Klärungsgespräch gebucht",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{participant.first_name}* hat nach dem Kennenlerngespräch mit *{coach}* "
                    f"ein Klärungsgespräch (Check In) gebucht."
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": booking_info,
            },
        },
    ]

    # Add Q&A answers if present
    if booking and (booking.clarification_category or booking.clarification_description):
        qa_parts = []
        if booking.clarification_category:
            qa_parts.append(f"*Anliegen:* {booking.clarification_category}")
        if booking.clarification_description:
            qa_parts.append(f"*Beschreibung:* {booking.clarification_description}")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(qa_parts),
            },
        })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🔎 *Profil*\n<{url_participant}|➡ Zum Profil von {participant.first_name}>",
        },
    })

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent clarification call booked Slack to BL contact {bl_contact}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending clarification call booked info to BL contact {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending clarification call booked info to BL contact {bl_contact}: {e}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
        raise


def send_clarification_call_booked_info_to_coach_slack(matching_attempt):
    """Notify the coach (via Slack) that the participant has booked a clarification call — nothing to do for them."""
    client = WebClient(token=settings.SLACK_BOT_TOKEN)

    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant

    user_id = coach.slack_user_id
    if not user_id:
        raise ValueError(f"Coach {coach} does not have a Slack user ID")

    subject = f"ℹ️ Kurzes Update zum Coaching mit {participant.first_name}"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"ℹ️ Kurzes Update zum Coaching mit {participant}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{participant.first_name}* hat nach dem Kennenlerngespräch mit Dir ein "
                    f"kurzes Klärungsgespräch mit uns gebucht, um noch ein paar Fragen zu klären."
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "Wir kümmern uns darum und klären alles direkt mit "
                    f"*{participant.first_name}*."
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "👉 *Für dich gibt es aktuell nichts zu tun.* "
                    "Sobald alles geklärt ist, melden wir uns mit den nächsten Schritten."
                ),
            },
        },
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent clarification call booked Slack to coach {coach}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error sending clarification call booked info to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending clarification call booked info to coach {coach}: {e}")
        create_slack_log(
            to=coach.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
        raise


def send_participant_intro_call_feedback_timeout_notification_to_staff_slack(matching_attempt):
    """Notify BL staff that the participant has not responded to the intro call feedback request even after the reminder."""
    client = WebClient(token=settings.SLACK_BOT_TOKEN)
    coach = matching_attempt.matched_coach
    participant = matching_attempt.participant
    bl_contact = matching_attempt.bl_contact
    url_participant = settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk})
    user_id = bl_contact.slack_user_id if bl_contact else None

    if not user_id:
        raise ValueError(f"BL contact for matching attempt {matching_attempt.id} does not have a Slack user ID")

    logger.info(
        f"Sending participant intro call feedback timeout staff notification Slack to BL contact "
        f"{bl_contact} (matching_attempt: {matching_attempt.id})"
    )
    subject = f"⚠️ {participant.first_name} hat nach dem Kennenlerngespräch nicht geantwortet"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ Keine Antwort von Teilnehmer:in nach Kennenlerngespräch",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{participant.first_name} {participant.last_name}* hat trotz Erinnerung bislang nicht bestätigt, "
                    f"ob das Coaching mit *{coach}* starten kann.\n\n"
                    f"Bitte nimm direkt Kontakt mit *{participant.first_name}* auf, um zu klären, ob das Coaching stattfinden soll."
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Teilnehmer:in:* <{url_participant}|{participant}>\n"
                    f"*Coach:* {coach}\n"
                ),
            },
        },
    ]

    message = _blocks_to_text(blocks)

    try:
        dm_channel = _open_dm_channel(client, user_id)
        client.chat_postMessage(channel=dm_channel, text=subject, blocks=blocks)
        logger.info(f"Successfully sent participant intro call feedback timeout staff notification Slack to {bl_contact}")
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message=message,
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
        )
    except SlackApiError as e:
        logger.error(
            f"Slack API error sending participant intro call feedback timeout notification to staff {bl_contact}: {e}"
        )
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error sending participant intro call feedback timeout notification to staff {bl_contact}: {e}"
        )
        create_slack_log(
            to=bl_contact.user,
            subject=subject,
            message="",
            matching_attempt=matching_attempt,
            sent_by=SlackLog.SentBy.SYSTEM,
            status=SlackLog.Status.FAILED,
            error_message=str(e),
        )
        raise

        raise