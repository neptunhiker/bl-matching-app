"""
Token utilities for coach (and future participant) action links sent in emails.

Public API
----------
generate_secure_token()
    Return a cryptographically secure URL-safe string suitable for use as a
    one-time action token in an email link.

consume_token(queryset, token_value)
    Atomically mark a token as used.  Returns (token_instance, already_used).
    Safe against concurrent double-clicks.

generate_coach_action_tokens(request_to_coach, request)
    Create one ACCEPT and one DECLINE CoachActionToken for the given
    RequestToCoach and return their absolute URLs as (accept_url, decline_url).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from django.urls import reverse
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import QuerySet


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

def generate_secure_token() -> str:
    """
    Return a cryptographically secure, URL-safe token string.

    Uses ``secrets.token_urlsafe(48)`` which produces a ~64-character string
    with ~384 bits of entropy — far beyond any brute-force concern.
    """
    return secrets.token_urlsafe(48)


# ---------------------------------------------------------------------------
# Token consumption (race-condition-safe)
# ---------------------------------------------------------------------------

def consume_token(queryset: "QuerySet", token_value: str) -> tuple:
    """
    Atomically mark a token as used and return it.

    Performs a single ``UPDATE … WHERE token=… AND used_at IS NULL`` so that
    only one concurrent request can ever win the update, preventing double
    submissions (e.g. a coach clicking the button twice in quick succession,
    or two browser tabs racing).

    Args:
        queryset:    A QuerySet for the token model (e.g.
                     ``CoachActionToken.objects.all()``).
        token_value: The raw token string from the URL.

    Returns:
        ``(token_instance, already_used)`` where:

        * ``token_instance`` is the model instance if the token exists in the
          DB at all, otherwise ``None``.
        * ``already_used`` is ``True`` when the token exists but ``used_at``
          was already set before this call (i.e. this is a duplicate request).

    Usage::

        token, already_used = consume_token(CoachActionToken.objects.all(), raw)
        if token is None:
            # Token does not exist → invalid/tampered link
            ...
        if already_used:
            # Token was already consumed → show "already responded" page
            ...
        # Token successfully consumed → proceed with status update
        ...
    """
    try:
        instance = queryset.get(token=token_value)
    except queryset.model.DoesNotExist:
        return None, False

    if instance.used_at is not None:
        # Already consumed before this request arrived.
        return instance, True

    # Atomic update: only succeeds if used_at is still NULL at DB level.
    # rows_updated will be 0 if another concurrent request beat us to it.
    rows_updated = (
        queryset
        .filter(token=token_value, used_at__isnull=True)
        .update(used_at=timezone.now())
    )

    if rows_updated == 0:
        # A concurrent request won the race — re-fetch to get the used_at value.
        instance.refresh_from_db()
        return instance, True

    instance.refresh_from_db()
    return instance, False


# ---------------------------------------------------------------------------
# Coach action URL generation
# ---------------------------------------------------------------------------

def generate_coach_action_tokens(request_to_coach) -> tuple[str, str]:
    """
    Create one ACCEPT token and one DECLINE token for *request_to_coach* and
    return their absolute URLs as ``(accept_url, decline_url)``.

    A new pair of tokens is created on every call, so each email (initial send
    + every reminder) gets its own fresh links.  Old tokens from earlier emails
    remain valid — the view's terminal-status guard prevents a coach from
    changing their answer after they have already responded.

    Absolute URLs are built using ``settings.SITE_URL`` so this function works
    correctly from management commands and cron jobs where no ``HttpRequest``
    is available.  Set ``SITE_URL`` in your ``.env`` file (no trailing slash):

        SITE_URL=https://yourdomain.com        # production
        SITE_URL=http://localhost:8000          # local dev (default)

    Args:
        request_to_coach: A ``RequestToCoach`` instance the tokens belong to.

    Returns:
        ``(accept_url, decline_url)`` — fully qualified URLs safe to embed
        directly in an email template.
    """
    from django.conf import settings  # noqa: PLC0415

    # Local import avoids a circular dependency:
    # models.py does not import from tokens.py, but keeping the import here
    # (rather than at module level) makes the dependency direction explicit.
    from .models import CoachActionToken  # noqa: PLC0415

    accept_token = CoachActionToken.objects.create(
        token=generate_secure_token(),
        request_to_coach=request_to_coach,
        action=CoachActionToken.Action.ACCEPT,
    )
    decline_token = CoachActionToken.objects.create(
        token=generate_secure_token(),
        request_to_coach=request_to_coach,
        action=CoachActionToken.Action.DECLINE,
    )

    site_url = settings.SITE_URL.rstrip('/')
    accept_url = site_url + reverse('coach_respond', kwargs={'token': accept_token.token})
    decline_url = site_url + reverse('coach_respond', kwargs={'token': decline_token.token})

    return accept_url, decline_url
