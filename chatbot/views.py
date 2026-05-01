import json
import logging

import markdown as _markdown
import openai
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import render
from django.views import View

from .system_prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_ALLOWED_ROLES = {"user", "assistant"}
_MAX_HISTORY_TURNS = 20  # cap history to avoid runaway token usage


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts the view to staff users only."""

    def test_func(self):
        return (
            self.request.user.is_active and self.request.user.is_staff
        ) or self.request.user.is_superuser


class ChatView(LoginRequiredMixin, StaffRequiredMixin, View):
    """
    Accepts a POST with a `message` field and optional `history` JSON field.
    Calls the IONOS Llama model and returns a rendered HTML fragment
    (chatbot/partials/message_bot.html) for HTMX to swap into the message list.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        user_message = request.POST.get("message", "").strip()
        raw_history = request.POST.get("history", "[]")

        error_reply = None

        if not user_message:
            error_reply = "Bitte gib eine Nachricht ein."

        history = []
        if not error_reply:
            try:
                parsed = json.loads(raw_history)
                if isinstance(parsed, list):
                    # Sanitise: only keep valid role/content pairs, cap length
                    for entry in parsed[-_MAX_HISTORY_TURNS:]:
                        if (
                            isinstance(entry, dict)
                            and entry.get("role") in _ALLOWED_ROLES
                            and isinstance(entry.get("content"), str)
                        ):
                            history.append(
                                {"role": entry["role"], "content": entry["content"]}
                            )
            except (json.JSONDecodeError, ValueError):
                # Ignore malformed history — start fresh
                history = []

        if not error_reply:
            messages = (
                [{"role": "system", "content": SYSTEM_PROMPT}]
                + history
                + [{"role": "user", "content": user_message}]
            )
            try:
                client = openai.OpenAI(
                    api_key=settings.IONOS_TOKEN,
                    base_url=settings.IONOS_BASE_URL,
                )
                response = client.chat.completions.create(
                    model=settings.IONOS_MODEL,
                    messages=messages,
                    stream=False,
                )
                assistant_reply = response.choices[0].message.content
                reply_html = _markdown.markdown(
                    assistant_reply,
                    extensions=['nl2br'],
                )
            except openai.AuthenticationError:
                logger.error("IONOS authentication failed — check IONOS_TOKEN_VALUE")
                error_reply = (
                    "Entschuldigung, die Verbindung zum KI-Dienst konnte nicht "
                    "hergestellt werden (Authentifizierungsfehler)."
                )
            except openai.APIConnectionError:
                logger.error("IONOS API connection error")
                error_reply = (
                    "Entschuldigung, ich konnte keine Verbindung herstellen. "
                    "Bitte überprüfe deine Internetverbindung und versuche es erneut."
                )
            except Exception as exc:
                logger.error("Unexpected chatbot error: %s", exc)
                error_reply = (
                    "Entschuldigung, ein unerwarteter Fehler ist aufgetreten. "
                    "Bitte versuche es erneut."
                )

        if error_reply:
            return render(
                request,
                "chatbot/partials/message_bot.html",
                {"reply": error_reply, "reply_html": f"<p>{error_reply}</p>", "is_error": True},
            )

        return render(
            request,
            "chatbot/partials/message_bot.html",
            {"reply": assistant_reply, "reply_html": reply_html, "is_error": False},
        )
