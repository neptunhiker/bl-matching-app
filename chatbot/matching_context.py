"""
Builds a German-language context block describing a MatchingAttempt.
Injected at the end of the chatbot system prompt so the model has full
awareness of the current matching state when answering staff questions.
"""
from __future__ import annotations

from django.utils import timezone

from matching.models import MatchingAttempt


def _fmt_dt(dt) -> str:
    """Format a datetime in Europe/Berlin local time as DD.MM.YYYY HH:MM."""
    if dt is None:
        return "—"
    return timezone.localtime(dt).strftime("%d.%m.%Y %H:%M")


def _fmt_date(d) -> str:
    if d is None:
        return "—"
    return d.strftime("%d.%m.%Y")


def build_matching_context(matching_attempt: MatchingAttempt) -> str:
    """
    Return a structured German Markdown text block for the given MatchingAttempt.
    Safe to call with any MatchingAttempt that has been fetched with appropriate
    select_related / prefetch_related; additional lazy queries may occur for
    events and clarification bookings.
    """
    now = timezone.now()
    ma = matching_attempt
    lines: list[str] = []

    lines += [
        "---",
        "",
        "## Matching-Kontext (aktuell)",
        "",
        "Du beantwortest Fragen zu **diesem spezifischen Matching**. "
        "Nutze die folgenden Informationen, um präzise und hilfreiche Antworten zu geben.",
        "",
        "### Allgemein",
        f"- **Status:** {ma.get_state_display()}",
        f"- **Erstellt am:** {_fmt_dt(ma.created_at)}",
        f"- **Genehmigte UE:** {ma.ue}",
        f"- **Automation:** {'aktiviert' if ma.automation_enabled else 'deaktiviert'}",
    ]

    if ma.bl_contact:
        lines.append(f"- **BL-Kontakt (Koordination):** {ma.bl_contact.user.first_name}")

    if ma.matched_coach:
        lines.append(f"- **Gematchter Coach:** {ma.matched_coach.first_name}")

    if ma.cancelled_at:
        lines.append(f"- **Abgebrochen am:** {_fmt_dt(ma.cancelled_at)}")

    # Participant fields (first name only; no email, last name, coaching target, or background info)
    p = ma.participant
    participant_lines: list[str] = []
    participant_lines.append(f"- **Vorname:** {p.first_name}")
    if p.start_date:
        participant_lines.append(f"- **Gewünschtes Startdatum:** {_fmt_date(p.start_date)}")

    if participant_lines:
        lines += ["", "### Teilnehmer:in"] + participant_lines

    # Deadlines
    deadline_lines: list[str] = []
    if ma.intro_call_deadline_at:
        overdue = " **(ÜBERSCHRITTEN)**" if ma.intro_call_deadline_at < now else ""
        deadline_lines.append(
            f"- **Intro-Call-Frist:** {_fmt_dt(ma.intro_call_deadline_at)}{overdue}"
        )
    if ma.participant_intro_call_feedback_deadline_at:
        overdue = (
            " **(ÜBERSCHRITTEN)**"
            if ma.participant_intro_call_feedback_deadline_at < now
            else ""
        )
        deadline_lines.append(
            f"- **TN-Feedback-Frist:** "
            f"{_fmt_dt(ma.participant_intro_call_feedback_deadline_at)}{overdue}"
        )

    if deadline_lines:
        lines += ["", "### Fristen"] + deadline_lines

    # Coach queue (all RTCs, ordered by priority)
    lines += ["", "### Coach-Warteschlange"]
    rtcs = list(ma.coach_requests.select_related("coach").order_by("priority"))
    if rtcs:
        for rtc in rtcs:
            sent_count = rtc.get_sent_count()
            reminders = max(sent_count - 1, 0)
            lines.append(
                f"- Priorität {rtc.priority}: **{rtc.coach.first_name}**"
                f" | Status: {rtc.get_state_display()}"
                f" | Coach-Status: {rtc.coach.get_status_display()}"
                f" | UE: {rtc.ue}"
                f" | Antwortfrist: {_fmt_dt(rtc.deadline_at)}"
                f" | Geantwortet: {_fmt_dt(rtc.responded_at)}"
                f" | Erinnerungen versendet: {reminders}"
            )
    else:
        lines.append("Keine Coach-Anfragen vorhanden.")

    # Active clarification call bookings
    active_bookings = list(
        ma.clarification_call_bookings.filter(status="active").order_by("-created_at")
    )
    if active_bookings:
        lines += ["", "### Klärungsgespräch-Buchung(en)"]
        for b in active_bookings:
            lines.append("- Status: aktiv")
            if b.start_time:
                lines.append(f"  - Termin: {_fmt_dt(b.start_time)}")
            if b.clarification_category:
                lines.append(f"  - Kategorie: {b.clarification_category}")
            if b.clarification_description:
                lines.append(f"  - Beschreibung: {b.clarification_description}")

    # Events log (chronological)
    lines += ["", "### Ereignis-Protokoll"]
    events = list(
        ma.matching_events.select_related("triggered_by_user").order_by("created_at")
    )
    if events:
        for ev in events:
            if ev.triggered_by_user:
                actor = ev.triggered_by_user.first_name or ev.triggered_by_user.username
            else:
                actor = ev.get_triggered_by_display()
            lines.append(
                f"- {_fmt_dt(ev.created_at)}: {ev.get_event_type_display()} "
                f"(ausgelöst von: {actor})"
            )
    else:
        lines.append("Keine Ereignisse bisher.")

    # Staff notes (oldest-first for chronological readability)
    notes = list(ma.notes.select_related("author").order_by("created_at"))
    if notes:
        lines += ["", "### Notizen (Koordination)"]
        for n in notes:
            author = n.author.first_name if n.author else "Unbekannt"
            lines.append(f"- {_fmt_dt(n.created_at)} ({author}): {n.body}")

    return "\n".join(lines)
