from django.db.models.signals import post_save
from django.dispatch import receiver
from matching.models import MatchingEvent
from matching.handlers.dispatcher import dispatch_event


@receiver(post_save, sender=MatchingEvent)
def matching_event_listener(sender, instance, created, **kwargs):
    if not created:
        return

    dispatch_event(instance)