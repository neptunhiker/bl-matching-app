import os
import requests

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse, HttpResponseServerError
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy

import uuid as _uuid

from django.utils.dateparse import parse_datetime

from .forms import ParticipantForm, CoachForm
from .models import Participant, Coach, Language, City, Industry

from matching.models import RequestToCoach, MatchingAttempt


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts access to active staff and superusers only."""
    def test_func(self):
        return (self.request.user.is_active and self.request.user.is_staff) or self.request.user.is_superuser


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'profiles/home.html'


# ---------------------------------------------------------------------------
# Participant CRUD
# ---------------------------------------------------------------------------

class ParticipantListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = Participant
    template_name = 'profiles/participant_list.html'
    context_object_name = 'participants'
    paginate_by = 25


class ParticipantDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Participant
    template_name = 'profiles/participant_detail.html'
    context_object_name = 'participant'
    
    def test_func(self):
        user = self.request.user
        return (user.is_active and user.is_staff) or user.is_superuser


class ParticipantCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = Participant
    form_class = ParticipantForm
    template_name = 'profiles/participant_form.html'

    # Q&A question texts used for prefill
    _LANGUAGE_QUESTION = "Auf welcher Sprache möchtest du das Coaching machen?"
    _COACHING_FORMAT = "Wie möchtest du dein Coaching am liebsten machen?"

    def get_initial(self):
        initial = super().get_initial()
        booking_pk = self.request.GET.get("booking")
        if not booking_pk:
            return initial

        from bookings.models import CalendlyBooking
        from .models import Language as LangModel

        try:
            booking = CalendlyBooking.objects.get(pk=booking_pk)
        except CalendlyBooking.DoesNotExist:
            return initial

        initial.update({
            "first_name": booking.invitee_first_name.lower().capitalize().strip(),
            "last_name":  booking.invitee_last_name.lower().capitalize().strip(),
            "email":      booking.invitee_email.strip(),
        })

        qa_map = {
            qa["question"].strip(): qa.get("answer", "")
            for qa in (booking.questions_and_answers or [])
            if "question" in qa
        }

        # Coaching format
        format_answer = qa_map.get(self._COACHING_FORMAT, "").strip()
        if format_answer:
            if format_answer.lower() in ["online", "präsenz", "hybrid"]:
                initial["coaching_format_online"] = format_answer.lower() == "online"
                initial["coaching_format_presence"] = format_answer.lower() == "präsenz"
                initial["coaching_format_hybrid"] = format_answer.lower() == "hybrid"
            
        
        # Language
        lang_answer = qa_map.get(self._LANGUAGE_QUESTION, "").strip()
        print(lang_answer)
        if lang_answer:
            matched = LangModel.objects.filter(name__iexact=lang_answer)
            if matched.exists():
                initial["languages"] = matched
        print(f"Prefilled languages: {initial.get('languages', [])}")

        return initial

    def get_success_url(self):
        return reverse_lazy('participant_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        booking_pk = self.request.GET.get("booking")
        if booking_pk:
            from bookings.models import CalendlyBooking
            try:
                booking = CalendlyBooking.objects.get(pk=booking_pk)
                self.object.calendly_booking = booking
                self.object.save(update_fields=["calendly_booking"])
            except CalendlyBooking.DoesNotExist:
                pass
        return response


class ParticipantUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = Participant
    form_class = ParticipantForm
    template_name = 'profiles/participant_form.html'

    def get_success_url(self):
        return reverse_lazy('participant_detail', kwargs={'pk': self.object.pk})


class ParticipantDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Participant
    template_name = 'profiles/participant_confirm_delete.html'
    context_object_name = 'participant'
    success_url = reverse_lazy('participant_list')


# ---------------------------------------------------------------------------
# Coach CRUD
# ---------------------------------------------------------------------------


class CoachListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = Coach
    template_name = 'profiles/coach_list.html'
    context_object_name = 'coaches'
    def get_queryset(self):
        from django.db.models import Case, When, Value, IntegerField
        qs = super().get_queryset().prefetch_related(
            'languages', 'coaching_cities', 'industry_experience'
        )

        # annotate specialism count for display in the table
        qs = qs.annotate(
            specialism_count=(
                Case(When(expert_for_job_applications=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(leadership_coaching=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(intercultural_coaching=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(high_profile_coaching=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(coaching_with_language_barriers=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(hr_experience=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(therapeutic_experience=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(adhs_coaching=True, then=Value(1)), default=Value(0), output_field=IntegerField()) +
                Case(When(lgbtq_coaching=True, then=Value(1)), default=Value(0), output_field=IntegerField())
            )
        )

        # text search (name / email)
        q = self.request.GET.get('q')
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(email__icontains=q)
            )

        # status filter
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        # language filter
        language = self.request.GET.get('language')
        if language:
            qs = qs.filter(languages__pk=language)

        # city filter
        city = self.request.GET.get('city')
        if city:
            qs = qs.filter(coaching_cities__pk=city)

        # industry filter
        industry = self.request.GET.get('industry')
        if industry:
            qs = qs.filter(industry_experience__pk=industry)

        # specialism filters (each checked box limits to coaches where that field is True)
        for field, _ in _SPECIALISM_CHOICES:
            if self.request.GET.get(f'spec_{field}'):
                qs = qs.filter(**{field: True})

        # own coaching room filter
        if self.request.GET.get('own_room'):
            qs = qs.filter(own_coaching_room=True)

        # coaching format filter (single-value: Online / Präsenz / Hybrid)
        fmt = self.request.GET.get('format')
        if fmt:
            qs = qs.filter(preferred_coaching_location=fmt)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # expose status choices for the filter form
        context['statuses'] = Coach.Status.choices
        context['Status'] = Coach.Status

        # filter option lists
        context['languages'] = Language.objects.all()
        context['cities'] = City.objects.all()
        context['industries'] = Industry.objects.all()
        context['specialism_choices'] = _SPECIALISM_CHOICES

        # selected values for form population
        context['q'] = self.request.GET.get('q', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_language'] = self.request.GET.get('language', '')
        context['selected_city'] = self.request.GET.get('city', '')
        context['selected_industry'] = self.request.GET.get('industry', '')
        context['selected_specialisms'] = [
            f for f, _ in _SPECIALISM_CHOICES if self.request.GET.get(f'spec_{f}')
        ]
        context['selected_own_room'] = bool(self.request.GET.get('own_room'))
        context['selected_format'] = self.request.GET.get('format', '')
        context['format_choices'] = [('Online', 'Online'), ('Präsenz', 'Präsenz'), ('Hybrid', 'Hybrid')]

        # Filter params without 'page' — used in pagination links to preserve active filters.
        params = self.request.GET.copy()
        params.pop('page', None)
        context['params'] = params

        # True when any filter param is active (used to distinguish "no results" from "empty DB")
        context['is_filtered'] = any([
            self.request.GET.get('q'),
            self.request.GET.get('status'),
            self.request.GET.get('language'),
            self.request.GET.get('city'),
            self.request.GET.get('industry'),
            self.request.GET.get('own_room'),
            self.request.GET.get('format'),
            *[self.request.GET.get(f'spec_{f}') for f, _ in _SPECIALISM_CHOICES],
        ])

        return context


class CoachDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Coach
    template_name = 'profiles/coach_detail.html'
    context_object_name = 'coach'

    def test_func(self):
        user = self.request.user
        return (user.is_active and user.is_staff) or user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['Status'] = Coach.Status
        return context


class CoachCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = Coach
    form_class = CoachForm
    template_name = 'profiles/coach_form.html'

    def get_success_url(self):
        return reverse_lazy('coach_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        self.object = form.save(commit=False)
        if not self.object.slack_user_id and self.object.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
            form.add_error('slack_user_id', 'Slack User ID ist erforderlich, wenn der bevorzugte Kommunikationskanal Slack ist.')
            return self.form_invalid(form)
        return super().form_valid(form)


class CoachUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = Coach
    form_class = CoachForm
    template_name = 'profiles/coach_form.html'

    def get_success_url(self):
        return reverse_lazy('coach_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        self.object = form.save(commit=False)
        if not self.object.slack_user_id and self.object.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
            form.add_error('slack_user_id', 'Slack User ID ist erforderlich, wenn der bevorzugte Kommunikationskanal Slack ist.')
            return self.form_invalid(form)
        return super().form_valid(form)


class CoachDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Coach
    template_name = 'profiles/coach_confirm_delete.html'
    context_object_name = 'coach'
    success_url = reverse_lazy('coach_list') 
    
    


_COACHING_HUB_API_URL = "https://coaching-hub.beginnerluft.de/api/v1/coaches/"

# Scalar fields synced directly from the API onto the Coach model (no M2M).
_COACH_SCALAR_FIELDS = [
    "first_name", "last_name", "email", "updated",
    "summary", "own_coaching_room", "preferred_coaching_location",
    "coaching_focus", "coaching_qualification", "coaching_methods",
    "education", "work_experience",
    "expert_for_job_applications", "leadership_coaching", "intercultural_coaching",
    "high_profile_coaching", "coaching_with_language_barriers", "hr_experience",
    "therapeutic_experience", "adhs_coaching", "lgbtq_coaching",
    "linkedin_url", "website_url",
    "preferred_communication_channel", "slack_user_id",
    "status", "status_notes", "maximum_capacity",
]

# Human-readable labels for changed-field display in the preview.
_FIELD_LABELS = {
    "first_name": "Vorname", "last_name": "Nachname", "email": "E-Mail",
    "updated": "Aktualisiert", "summary": "Zusammenfassung",
    "own_coaching_room": "Eigener Coaching-Raum",
    "preferred_coaching_location": "Coaching-Ort",
    "coaching_focus": "Fokus", "coaching_qualification": "Qualifikation",
    "coaching_methods": "Methoden", "education": "Ausbildung",
    "work_experience": "Berufserfahrung",
    "expert_for_job_applications": "Job-Bewerbungen",
    "leadership_coaching": "Führungscoaching",
    "intercultural_coaching": "Interkulturelles Coaching",
    "high_profile_coaching": "High-Profile", "coaching_with_language_barriers": "Sprachbarrieren",
    "hr_experience": "HR-Erfahrung", "therapeutic_experience": "Therapeutische Erfahrung",
    "adhs_coaching": "ADHS-Coaching", "lgbtq_coaching": "LGBTQ+ Coaching",
    "linkedin_url": "LinkedIn", "website_url": "Website",
    "preferred_communication_channel": "Kanal", "slack_user_id": "Slack ID",
    "status": "Status", "status_notes": "Status-Kommentar", "maximum_capacity": "Max. Kapazität",
}

# (field_name, human-readable label) for each boolean specialism on Coach.
_SPECIALISM_CHOICES = [
    ("expert_for_job_applications", "Job-Bewerbungen"),
    ("leadership_coaching", "Führungscoaching"),
    ("intercultural_coaching", "Interkulturelles Coaching"),
    ("high_profile_coaching", "High-Profile"),
    ("coaching_with_language_barriers", "Sprachbarrieren"),
    ("hr_experience", "HR-Erfahrung"),
    ("therapeutic_experience", "Therapeutische Erfahrung"),
    ("adhs_coaching", "ADHS-Coaching"),
    ("lgbtq_coaching", "LGBTQ+ Coaching"),
]


def _fetch_coaches_from_api():
    """
    Call the Coaching Hub API and return a list of raw dicts.

    Handles both a bare list response and a paginated {"results": [...]} shape.
    Raises requests.RequestException on network/HTTP errors.
    """
    api_key = os.environ.get("COACHING_HUB_API_KEY")
    if not api_key:
        raise ValueError("COACHING_HUB_API_KEY is not configured.")

    headers = {"Authorization": f"Api-Key {api_key}"}
    response = requests.get(_COACHING_HUB_API_URL, headers=headers, timeout=10)
    response.raise_for_status()

    data = response.json()
    # Support both bare-list and paginated {"results": [...]} shapes
    if isinstance(data, list):
        return data
    return data.get("results", [])


_VALID_STATUSES = {c[0] for c in Coach.Status.choices}
_VALID_CHANNELS = {c[0] for c in Coach.CommunicationChannel.choices}


def _parse_api_coach(item):
    """Extract and validate all importable fields from a single API coach item.

    Scalar fields are keyed by their model field name.
    M2M relations are returned under '_languages', '_coaching_cities',
    '_industry_experience' as lists of name strings.
    coaching_hub_id comes from item['id'] (UUID).
    """
    email = (item.get("email") or "").strip().lower()

    raw_channel = (item.get("preferred_communication_channel") or "").strip().lower()
    channel = raw_channel if raw_channel in _VALID_CHANNELS else Coach.CommunicationChannel.SLACK

    raw_status = (item.get("status") or "").strip().lower()
    status = raw_status if raw_status in _VALID_STATUSES else Coach.Status.ONBOARDING

    raw_capacity = item.get("maximum_capacity")
    try:
        capacity = int(raw_capacity) if raw_capacity is not None else None
    except (TypeError, ValueError):
        capacity = None

    raw_hub_id = item.get("id") or ""
    try:
        coaching_hub_id = _uuid.UUID(str(raw_hub_id)) if raw_hub_id else None
    except (ValueError, AttributeError):
        coaching_hub_id = None

    updated = parse_datetime(item["updated"]) if item.get("updated") else None

    own_room_raw = (item.get("own_coaching_room") or "").strip().lower()
    own_coaching_room = own_room_raw == "ja"

    return {
        "coaching_hub_id": coaching_hub_id,
        "email": email,
        "first_name": (item.get("first_name") or "").strip(),
        "last_name": (item.get("last_name") or "").strip(),
        "updated": updated,
        "summary": (item.get("summary") or "").strip(),
        "own_coaching_room": own_coaching_room,
        "preferred_coaching_location": (item.get("preferred_coaching_location") or "").strip(),
        "coaching_focus": (item.get("coaching_focus") or "").strip(),
        "coaching_qualification": (item.get("coaching_qualification") or "").strip(),
        "coaching_methods": (item.get("coaching_methods") or "").strip(),
        "education": (item.get("education") or "").strip(),
        "work_experience": (item.get("work_experience") or "").strip(),
        "expert_for_job_applications": bool(item.get("expert_for_job_applications", False)),
        "leadership_coaching": bool(item.get("leadership_coaching", False)),
        "intercultural_coaching": bool(item.get("intercultural_coaching", False)),
        "high_profile_coaching": bool(item.get("high_profile_coaching", False)),
        "coaching_with_language_barriers": bool(item.get("coaching_with_language_barriers", False)),
        "hr_experience": bool(item.get("hr_experience", False)),
        "therapeutic_experience": bool(item.get("therapeutic_experience", False)),
        "adhs_coaching": bool(item.get("adhs_coaching", False)),
        "lgbtq_coaching": bool(item.get("lgbtq_coaching", False)),
        "linkedin_url": (item.get("linkedin_url") or "").strip(),
        "website_url": (item.get("website_url") or "").strip(),
        "preferred_communication_channel": channel,
        "slack_user_id": (item.get("slack_user_id") or "").strip(),
        "status": status,
        "status_notes": (item.get("status_notes") or "").strip(),
        "maximum_capacity": capacity,
        # M2M — lists of name strings, resolved to model instances separately
        "_languages": [n.strip() for n in (item.get("language") or []) if isinstance(n, str) and n.strip()],
        "_coaching_cities": [n.strip() for n in (item.get("coaching_cities") or []) if isinstance(n, str) and n.strip()],
        "_industry_experience": [n.strip() for n in (item.get("industry_experience") or []) if isinstance(n, str) and n.strip()],
    }


def _resolve_m2m_names(model, names):
    """Return a list of model instances, creating any that don't exist yet."""
    instances = []
    for name in names:
        if name:
            obj, _ = model.objects.get_or_create(name=name)
            instances.append(obj)
    return instances


def _lookup_coach(parsed):
    """Find an existing Coach for the parsed item, or return None.

    Prefers coaching_hub_id lookup; falls back to email for records
    created before coaching_hub_id was introduced.
    """
    if parsed["coaching_hub_id"]:
        try:
            return Coach.objects.get(coaching_hub_id=parsed["coaching_hub_id"])
        except Coach.DoesNotExist:
            pass
    if parsed["email"]:
        try:
            return Coach.objects.get(email=parsed["email"])
        except Coach.DoesNotExist:
            pass
    return None


def _changed_scalar_fields(coach, parsed):
    """Return list of (field_name, label) pairs that differ between DB and API."""
    changed = []
    for field in _COACH_SCALAR_FIELDS:
        if field not in parsed:
            continue
        db_val = getattr(coach, field, None)
        api_val = parsed[field]
        if db_val != api_val:
            changed.append((field, _FIELD_LABELS.get(field, field)))
    return changed


def _apply_parsed_to_coach(coach, parsed):
    """Write all scalar fields from parsed dict onto a Coach instance and save."""
    for field in _COACH_SCALAR_FIELDS:
        if field in parsed:
            setattr(coach, field, parsed[field])
    # Always stamp the external ID when the API provides one.
    if parsed.get("coaching_hub_id"):
        coach.coaching_hub_id = parsed["coaching_hub_id"]
    coach.save()


def _set_m2m(coach, parsed):
    """Set all M2M relations on coach from the parsed name lists."""
    coach.languages.set(_resolve_m2m_names(Language, parsed.get("_languages", [])))
    coach.coaching_cities.set(_resolve_m2m_names(City, parsed.get("_coaching_cities", [])))
    coach.industry_experience.set(_resolve_m2m_names(Industry, parsed.get("_industry_experience", [])))


@login_required
def coach_import_preview(request):
    """GET — fetch coaches from the API, diff against the DB, show preview."""
    if not (request.user.is_staff or request.user.is_superuser):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    try:
        api_coaches = _fetch_coaches_from_api()
    except ValueError as exc:
        return _render_preview_error(request, str(exc))
    except requests.RequestException as exc:
        return _render_preview_error(request, f"Die Coaching-Hub-API ist nicht erreichbar: {exc}")

    new_coaches = []
    updated_coaches = []   # list of {"parsed": ..., "changed": [(field, label), ...]}
    unchanged_coaches = []

    for item in api_coaches:
        if not (item.get("email") or "").strip():
            continue
        parsed = _parse_api_coach(item)
        existing = _lookup_coach(parsed)
        if existing is None:
            new_coaches.append(parsed)
        else:
            changed = _changed_scalar_fields(existing, parsed)
            if changed:
                updated_coaches.append({"parsed": parsed, "changed": changed})
            else:
                unchanged_coaches.append(parsed)

    from django.shortcuts import render
    return render(request, "profiles/coach_import_preview.html", {
        "new_coaches": new_coaches,
        "updated_coaches": updated_coaches,
        "unchanged_coaches": unchanged_coaches,
        "actionable_count": len(new_coaches) + len(updated_coaches),
    })


def _render_preview_error(request, message):
    from django.shortcuts import render
    return render(request, "profiles/coach_import_preview.html", {
        "api_error": message,
        "new_coaches": [],
        "updated_coaches": [],
        "unchanged_coaches": [],
    })


@login_required
def coach_import_confirm(request):
    """POST — re-fetch from API and upsert selected coaches."""
    if not (request.user.is_staff or request.user.is_superuser):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    if request.method != "POST":
        from django.shortcuts import redirect
        return redirect("get_coaches")

    # hub_ids submitted from the preview form (new + updated coaches).
    submitted_hub_ids = {
        s.strip() for s in request.POST.getlist("hub_ids") if s.strip()
    }

    if not submitted_hub_ids:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.info(request, "Es wurden keine Coaches zum Importieren ausgewählt.")
        return redirect("coach_list")

    # Re-fetch from API — never trust raw POST data for field values.
    try:
        api_coaches = _fetch_coaches_from_api()
    except (ValueError, requests.RequestException) as exc:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, f"Import fehlgeschlagen – API nicht erreichbar: {exc}")
        return redirect("coach_list")

    created_count = 0
    updated_count = 0

    for item in api_coaches:
        parsed = _parse_api_coach(item)
        hub_id_str = str(parsed["coaching_hub_id"]) if parsed["coaching_hub_id"] else None
        if hub_id_str not in submitted_hub_ids:
            continue

        existing = _lookup_coach(parsed)
        if existing:
            _apply_parsed_to_coach(existing, parsed)
            _set_m2m(existing, parsed)
            updated_count += 1
        else:
            if not parsed["email"]:
                continue
            coach = Coach(email=parsed["email"])
            _apply_parsed_to_coach(coach, parsed)
            _set_m2m(coach, parsed)
            created_count += 1

    from django.contrib import messages
    from django.shortcuts import redirect
    parts = []
    if created_count:
        parts.append(f"{created_count} neu importiert")
    if updated_count:
        parts.append(f"{updated_count} aktualisiert")
    if parts:
        messages.success(request, f"Import abgeschlossen: {', '.join(parts)}.")
    else:
        messages.info(request, "Keine Änderungen vorgenommen.")
    return redirect("coach_list")