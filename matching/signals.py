import logging

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import RequestToCoach
from .notifications import send_connecting_email

logger = logging.getLogger(__name__)

_ACCEPTED_STATUSES = {
    RequestToCoach.Status.ACCEPTED_ON_TIME,
}
_AWAITING_REPLY_STATUSES = {
    RequestToCoach.Status.AWAITING_REPLY,
}


@receiver(pre_save, sender=RequestToCoach)
def on_request_to_coach_accepted(sender, instance, **kwargs):
    """Fire a connecting email to both parties when a coach accepts a request."""
    logger.debug(
        "pre_save RequestToCoach pk=%s: checking status transition",
        instance.pk,
    )

    if not instance.pk:
        logger.debug("pre_save: new instance (no pk), skipping")
        return

    try:
        previous = RequestToCoach.objects.get(pk=instance.pk)
    except RequestToCoach.DoesNotExist:
        logger.debug("pre_save: RequestToCoach pk=%s not found in DB, skipping", instance.pk)
        return

    logger.debug(
        "pre_save: status %r -> %r (accepted=%s, awaiting=%s)",
        previous.status,
        instance.status,
        instance.status in _ACCEPTED_STATUSES,
        previous.status in _AWAITING_REPLY_STATUSES,
    )

    if previous.status in _AWAITING_REPLY_STATUSES and instance.status in _ACCEPTED_STATUSES:
        logger.info(
            "RequestToCoach pk=%s accepted — firing send_connecting_email",
            instance.pk,
        )
        send_connecting_email(instance)
    else:
        logger.debug(
            "pre_save: no transition to accepted detected, not sending connecting email"
        )
