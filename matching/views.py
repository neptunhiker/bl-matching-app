import os

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Max, Q

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.views.generic import DetailView, ListView, CreateView, View, UpdateView, DeleteView, TemplateView
from urllib3 import request
from urllib.parse import urlparse


from matching.tests.conftest import matching_attempt
from profiles.models import Coach
from .models import CoachActionToken, MatchingAttempt, RequestToCoach, MatchingEvent, TriggeredByOptions, ParticipantActionToken
from .tokens import consume_token
from matching import services
from django.utils import dateparse
import json


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts the view to staff users only."""
    def test_func(self):
        return (self.request.user.is_active and self.request.user.is_staff) or self.request.user.is_superuser


class MatchingAttemptCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = MatchingAttempt
    fields = ['participant', 'ue', 'bl_contact']
    template_name = 'matching/matching_attempt_form.html'

    def form_valid(self, form):
        participant = form.cleaned_data["participant"]
        ue = form.cleaned_data["ue"]
        bl_contact = form.cleaned_data.get("bl_contact")



        if ue < 1:
            messages.error(self.request, "Die Anzahl der Unterrichtseinheiten muss mindestens 1 sein.")
            return self.form_invalid(form)

        try:
            self.object = services.create_matching_attempt(
                participant=participant,
                ue=ue,
                bl_contact=bl_contact,
                created_by=self.request.user,
            )

        except ValidationError as e:
            existing = e.message if hasattr(e, "message") else None

            if existing:
                messages.error(
                    self.request,
                    format_html(
                        "Konnte Matching nicht erstellen: es existiert bereits ein <a href='{}' style='text-decoration:underline'>aktives Matching</a> für {}.",
                        existing.get_absolute_url(),
                        participant,
                    ),
                )
            else:
                messages.error(self.request, "Es existiert bereits ein aktives Matching.")

            return self.form_invalid(form)

        except IntegrityError:
            conflicting = MatchingAttempt.objects.filter(
                participant=participant,
                state__in=MatchingAttempt.ACTIVESTATES, 
            ).order_by("-created_at").first()

            if conflicting:
                messages.error(
                    self.request,
                    format_html(
                        "Konnte Matching nicht erstellen: es existiert bereits ein <a href='{}' style='text-decoration:underline'>aktives Matching</a> für {}.",
                        conflicting.get_absolute_url(),
                        participant,
                    ),
                )
            else:
                messages.error(
                    self.request,
                    "Konnte Matching nicht erstellen: bereits ein aktives Matching vorhanden."
                )
            return self.form_invalid(form)

        return redirect(self.object.get_absolute_url())
    
       
        

    def get_success_url(self):
        return reverse('matching_attempt_detail', kwargs={'pk': self.object.pk})


class MatchingAttemptDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = MatchingAttempt
    template_name = 'matching/matching_attempt_detail.html'
    context_object_name = 'matching_attempt'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        matching_attempt = self.object
        # Collect emails (direct on matching + per-request) and slack logs, then merge
        direct_emails = list(matching_attempt.email_logs.all().select_related('request_to_coach'))
        coach_emails = []
        for req in matching_attempt.coach_requests.all().select_related('coach'):
            for email in req.email_logs.all().select_related('request_to_coach'):
                coach_emails.append(email)
        all_emails = sorted(
            direct_emails + coach_emails,
            key=lambda e: e.sent_at,
            reverse=True,
        )
        # Slack logs (direct + per-request)
        direct_slack = list(matching_attempt.slack_logs.all().select_related('to'))
        coach_slack = []
        for req in matching_attempt.coach_requests.all().select_related('coach'):
            for s in req.slack_logs.all().select_related('to'):
                coach_slack.append(s)
        all_slack = sorted(
            direct_slack + coach_slack,
            key=lambda s: s.sent_at,
            reverse=True,
        )

        # Build unified notifications list with type markers so template can render both
        notifications = []
        for e in all_emails:
            notifications.append({
                'type': 'email',
                'obj': e,
                'sent_at': e.sent_at,
            })
        for s in all_slack:
            notifications.append({
                'type': 'slack',
                'obj': s,
                'sent_at': s.sent_at,
            })
        notifications = sorted(notifications, key=lambda n: n['sent_at'], reverse=True)

        context['all_emails'] = all_emails
        context['all_slack'] = all_slack
        context['notifications'] = notifications
        # context['transitions'] = list(
        #     matching_attempt.transitions.order_by('-created_at')
        # )

        context['events'] = matching_attempt.matching_events.order_by('-created_at')
        
        context['show_start_button'] = (
            self.request.user.is_staff
            and matching_attempt.automation_enabled
            and matching_attempt.coach_requests.count() > 0
            and matching_attempt.state in ["in_preparation"]
        )
        
        context['show_resume_button'] = (
            self.request.user.is_staff
            and matching_attempt.automation_enabled
            and matching_attempt.coach_requests.count() > 0
            and matching_attempt.state in ["failed"]
        )

        return context
    
class MatchingAttemptDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = MatchingAttempt
    template_name = "matching/matching_attempt_delete.html"
    success_url = reverse_lazy("matching_attempts")

    def test_func(self):
        return self.request.user.is_staff

class StartMatchingView(LoginRequiredMixin, StaffRequiredMixin, View):
    """Transition a MatchingAttempt from DRAFT → READY_FOR_MATCHING.

    POST /matching/<pk>/start/
    """

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        matching_attempt.start_matching(
            triggered_by_user=request.user,
        )
        matching_attempt.save()
       
        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))
    
class ResumeMatchingView(LoginRequiredMixin, StaffRequiredMixin, View):
    """Transition a MatchingAttempt from FAILED → READY_FOR_MATCHING.

    POST /matching/<pk>/resume/
    """

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        matching_attempt.resume_matching(
            triggered_by_user=request.user,
        )
        matching_attempt.save()
       
        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))


class ToggleAutomationView(LoginRequiredMixin, StaffRequiredMixin, View):
    """Enable or disable automation on a MatchingAttempt.

    POST /matching/<pk>/automation/
    Body: action=enable  or  action=disable
    """

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        action = request.POST.get("action")

        if action == "enable":
            matching_attempt.enable_automation(triggered_by_user=request.user)
        elif action == "disable":
            matching_attempt.disable_automation(triggered_by_user=request.user)

        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))



class RequestToCoachCreateView(LoginRequiredMixin, StaffRequiredMixin, View):
    """Create a new RequestToCoach for a given MatchingAttempt.

    GET  /matching/<pk>/add-coach/   → render form
    POST /matching/<pk>/add-coach/   → validate & create, redirect to detail
    """

    def _next_priority(self, matching_attempt):
        agg = matching_attempt.coach_requests.aggregate(max_p=Max("priority"))
        current_max = agg["max_p"]
        return (current_max + 10) if current_max is not None else 10

    def get(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        available_coaches = Coach.objects.available().select_related('user').order_by('user__last_name', 'user__first_name')
        return render(request, "matching/request_to_coach_form.html", {
            "matching_attempt": matching_attempt,
            "next_priority": self._next_priority(matching_attempt),
            "available_coaches": available_coaches,
        })

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        coach_id = request.POST.get("coach_id", "").strip()
        max_requests = request.POST.get("max_number_of_requests", "3").strip()
        posted_priority = request.POST.get("priority", "").strip()
        ue = request.POST.get("ue", "").strip()
        
        errors = {}

        coach = None
        if not coach_id:
            errors["coach"] = "Bitte einen Coach auswählen."
        else:
            try:
                coach = Coach.objects.get(pk=coach_id)
            except (Coach.DoesNotExist, ValueError):
                errors["coach"] = "Ungültiger Coach."
                coach = None
        # Only check status if coach is valid and no previous coach error
        if coach and "coach" not in errors:
            if coach.status != Coach.Status.AVAILABLE:
                errors["coach"] = f"Coach {coach.full_name} ist derzeit nicht verfügbar (Status: {coach.get_status_display()})."

        if coach and "coach" not in errors:
            # Double-check that the coach doesn't already have a request for this matching attempt to prevent races
            if matching_attempt.coach_requests.filter(coach=coach).exists():
                errors["coach"] = f"Coach {coach.full_name} hat bereits eine Anfrage für dieses Matching."

        try:
            max_requests = int(max_requests)
            if max_requests < 1:
                raise ValueError
        except (ValueError, TypeError):
            errors["max_number_of_requests"] = "Muss eine positive Zahl sein."

        # Priority: optional override; must be integer >= 1 and unique per matching_attempt
        priority = None
        if posted_priority:
            try:
                priority = int(posted_priority)
                if priority < 1:
                    raise ValueError
            except (ValueError, TypeError):
                errors["priority"] = "Muss eine ganze Zahl >= 1 sein."
        else:
            priority = self._next_priority(matching_attempt)

        if "priority" not in errors:
            existing = list(matching_attempt.coach_requests.values_list("priority", flat=True))
            if priority in existing:
                existing_sorted = ", ".join(str(p) for p in sorted(existing)) if existing else "keine"
                errors["priority"] = (
                    f"Diese Priorität ist bereits vergeben. Bestehende Prioritäten: {existing_sorted}"
                )
                
        if "ue" not in errors:
            try:
                ue = int(ue)
                if ue < 1:
                    raise ValueError
                if ue > matching_attempt.ue:
                    errors["ue"] = f"Der Coach darf keinen Coaching-Auftrag erhalten, der mehr UE ({ue}) als die insgesamt genehmigten UE ({matching_attempt.ue}) hat."
            except (ValueError, TypeError):
                errors["ue"] = "Muss eine positive Zahl sein."

        if errors:
            available_coaches = Coach.objects.available().select_related('user').order_by('user__last_name', 'user__first_name')
            return render(request, "matching/request_to_coach_form.html", {
                "pk": pk,
                "matching_attempt": matching_attempt,
                "next_priority": self._next_priority(matching_attempt),
                "errors": errors,
                "posted_coach_name": request.POST.get("coach_name", ""),
                "posted_coach_id": coach_id,
                "posted_max_requests": request.POST.get("max_number_of_requests", "3"),
                "ue": request.POST.get("ue", ""),
                "posted_priority": request.POST.get("priority", ""),
                "available_coaches": available_coaches,
            })
        # priority has been validated above (either user-supplied or auto-assigned)
        services.create_request_to_coach(
            matching_attempt=matching_attempt,
            coach=coach,
            priority=priority,
            ue=ue,
            max_number_of_requests=max_requests,
            triggered_by=TriggeredByOptions.STAFF,
            triggered_by_user=request.user,
        )

        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))


class RequestToCoachUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = RequestToCoach
    fields = ['priority', 'max_number_of_requests']
    template_name = 'matching/request_to_coach_edit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rtc = self.object
        matching_attempt = rtc.matching_attempt
        existing = sorted(matching_attempt.coach_requests.exclude(pk=rtc.pk).values_list('priority', flat=True))
        context.update({
            'matching_attempt': matching_attempt,
            'existing_priorities': existing,
        })
        return context

    def form_valid(self, form):
        priority = form.cleaned_data.get('priority')
        if priority is None or int(priority) < 1:
            form.add_error('priority', 'Muss eine ganze Zahl >= 1 sein.')
            return self.form_invalid(form)

        matching_attempt = self.object.matching_attempt
        if matching_attempt.coach_requests.exclude(pk=self.object.pk).filter(priority=priority).exists():
            existing = matching_attempt.coach_requests.exclude(pk=self.object.pk).values_list('priority', flat=True)
            existing_sorted = ", ".join(str(p) for p in sorted(existing)) if existing else 'keine'
            form.add_error('priority', f'Diese Priorität ist bereits vergeben. Bestehende Prioritäten: {existing_sorted}')
            return self.form_invalid(form)

        response = super().form_valid(form)
        return response

    def get_success_url(self):
        # Prefer explicit `next` parameter (POST or GET) to return to the originating page.
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('matching_attempt_detail', kwargs={'pk': self.object.matching_attempt.pk})


class RequestToCoachDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = RequestToCoach
    template_name = 'matching/request_to_coach_confirm_delete.html'
    
    def post(self, request, *args, **kwargs):
        from matching.services import create_matching_event
        
        self.object = self.get_object()
        create_matching_event(
            matching_attempt=self.object.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_DELETED,
            triggered_by=TriggeredByOptions.STAFF,
            triggered_by_user=request.user,
            payload={
                "rtc_id": str(self.object.id),
            }
        )
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        # Allow deletion to redirect back to an explicit `next` parameter when present.
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            # Protect against redirecting to the deleted object's detail page.
            # Accept both absolute and relative URLs by comparing path parts.
            try:
                parsed = urlparse(next_url)
                next_path = parsed.path
            except Exception:
                next_path = next_url

            own_detail_path = reverse('request_to_coach_detail', kwargs={'pk': self.object.pk})
            if next_path and next_path != own_detail_path:
                return next_url

        return reverse('matching_attempt_detail', kwargs={'pk': self.object.matching_attempt.pk})


class MatchingAttemptListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    model = MatchingAttempt
    template_name = 'matching/matchings.html'
    context_object_name = 'matching_attempts'
    
class RequestToCoachDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = RequestToCoach
    template_name = 'matching/request_to_coach_detail.html'
    context_object_name = 'request_to_coach'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # collect email and slack logs for this request and provide unified notifications
        email_logs = list(self.object.email_logs.order_by('-sent_at').select_related('request_to_coach__coach'))
        slack_logs = list(self.object.slack_logs.order_by('-sent_at').select_related('request_to_coach__coach'))

        notifications = []
        for e in email_logs:
            notifications.append({'type': 'email', 'obj': e, 'sent_at': e.sent_at})
        for s in slack_logs:
            notifications.append({'type': 'slack', 'obj': s, 'sent_at': s.sent_at})
        notifications = sorted(notifications, key=lambda n: n['sent_at'], reverse=True)

        context['email_logs'] = email_logs
        context['slack_logs'] = slack_logs
        context['notifications'] = notifications

        context['events'] = list(
            self.object.events.order_by('-created_at')
        )
        return context


class CoachRespondView(View):
    """Handles coach accept/decline action links sent in invitation emails.

    Public — no login required. The token in the URL is the sole authorisation.

    GET /matching/response_coach/<token>/

    Decision tree
    -------------
    1. Token not found in DB          → coach_response_invalid.html
    2. Token already used (used_at set) → response_already_used.html
    3. RequestToCoach already resolved  → response_already_used.html
       (coach replied via a different email's token — e.g. accepted email 1,
       then clicked the decline link in the reminder email)
    4. Determine on-time vs. late:
         now <= deadline  → ACCEPTED_ON_TIME / REJECTED_ON_TIME
         now >  deadline  → ACCEPTED_LATE    / REJECTED_LATE
         no deadline set  → treat as on-time (safe fallback)
    5. Save new status and render coach_response_after_intro_call.html
    """

    # States that mean the coach has already given a definitive answer.
    TERMINAL_STATES = {
        RequestToCoach.State.ACCEPTED,
        RequestToCoach.State.REJECTED,
    }

    def get(self, request, token):
        # ── 1. Look up token ────────────────────────────────────────────────
        token_instance, already_used = consume_token(
            CoachActionToken.objects.select_related(
                'request_to_coach__coach__user',
                'request_to_coach__matching_attempt__participant',
            ),
            token,
        )

        if token_instance is None:
            return render(request, 'matching/response_invalid_token.html', status=200)

        rtc = token_instance.request_to_coach
        coach = rtc.coach
        participant = rtc.matching_attempt.participant

        base_context = {
            'coach_name': coach.full_name,
            'participant_name': f"{participant.first_name} {participant.last_name}",
            'participant_first_name': participant.first_name,
            'coach': coach,
        }

        # ── 2. Token already consumed ────────────────────────────────────────
        if already_used:
            return render(
                request,
                'matching/response_already_used.html',
                {**base_context, 'previous_state': rtc.get_state_display()},
            )

        # ── 3. RequestToCoach already in a terminal state ────────────────────
        if rtc.state in self.TERMINAL_STATES:
            return render(
                request,
                'matching/response_already_used.html',
                {**base_context, 'previous_state': rtc.get_state_display()},
            )

        # ── 4 & 5. Determine update state ────────────────────────
        is_accept = token_instance.action == CoachActionToken.Action.ACCEPT
        
        now = timezone.now()
        deadline = rtc.deadline_at
        on_time = (deadline is None) or (now <= deadline)
        
        services.accept_or_decline_request_to_coach(
            rtc=rtc,
            accept=is_accept,
            response_time=timezone.now(),
            responded_by_user=coach.user,
        )


        return render(
            request,
            'matching/coach_response_matching_request.html',
            {
                **base_context,
                'action': token_instance.action, # 'accept' or 'decline'
                'is_accept': is_accept,
                'on_time': on_time,
                'deadline': rtc.deadline_at,
            },
        )

class ParticipantRespondView(View):
    """Handles participant response for their answer after Intro-Call with coach to check whether the coaching can start or whether they still have a clarification need.

    Public — no login required. The token in the URL is the sole authorisation.

    GET /matching/response_participant/<token>/

    Decision tree
    -------------
    1. Token not found in DB          → participant_response_invalid.html
    2. Token already used (used_at set) → participant_response_already_used.html
    3. MatchingAttempt already resolved  → participant_response_already_used.html
       (participant replied via a different email's token — e.g. accepted email 1,
       then clicked the decline link in the reminder email)
    4. Determine on-time vs. late:
         not implemented yet as no deadline yet
    5. Save new status and render participant_response_success.html
    """

    # States that mean the participant has already given a definitive answer.
    TERMINAL_STATES = {
        MatchingAttempt.State.MATCHING_COMPLETED,
        MatchingAttempt.State.CLARIFICATION_WITH_PARTICIPANT_NEEDED,
    }

    def get(self, request, token):
        # ── 1. Look up token ────────────────────────────────────────────────
        token_instance, already_used = consume_token(
            ParticipantActionToken.objects.select_related(
                'matching_attempt__matched_coach__user',
                'matching_attempt__participant',
            ),
            token,
        )

        if token_instance is None:
            return render(request, 'matching/participant_response_invalid_token.html', status=200)

        matching_attempt = token_instance.matching_attempt
        coach = matching_attempt.matched_coach
        participant = matching_attempt.participant

        base_context = {
            'coach': coach,
            'participant': participant,
        }

        # ── 2. Token already consumed ────────────────────────────────────────
        if already_used:
            return render(
                request,
                'matching/response_already_used.html',
                {**base_context},
            )

        # ── 3. MatchingAttempt already in a terminal state ────────────────────
        if matching_attempt.state in self.TERMINAL_STATES:
            return render(
                request,
                'matching/participant_response_already_used.html',
                {**base_context},
            )

        # ── 4 & 5. Determine update state ────────────────────────
        coaching_can_start = token_instance.action == ParticipantActionToken.Action.START_COACHING
        
        services.continue_matching_after_participant_responded_to_intro_call_feedback(
            matching_attempt=matching_attempt,
            coaching_can_start=coaching_can_start,
            response_time=timezone.now(),
            responded_by_participant=participant,
        )

        if coaching_can_start:
            return render(
                request,
                'matching/participant_response_coaching_can_start.html',
                {
                    **base_context,
                    'action': token_instance.action,
                    'coacing_can_start': coaching_can_start,
                },
            )
        else:
            return render(
                request,
                'matching/participant_response_clarification_needed.html',
                {
                    **base_context,
                    'action': token_instance.action,
                    'coacing_can_start': coaching_can_start,
                    'bl_contact': matching_attempt.bl_contact,
                },
            )



class ConfirmIntroCallView(View):
    """Handles coach confirmation of intro call completion.

    Public — no login required. The token in the URL is the sole authorisation.

    Decision tree
    -------------
    1. Look up token in DB
    2. If token not found → render invalid token page
    3. If token already used (used_at set) → render already used page
    4. If MatchingAttempt already in a terminal state → render already used page with previous status
    5. Otherwise, transition MatchingAttempt to READY_FOR_START_EMAIL and render success page"""


    # States that mean that the matching has been completed already
    TERMINAL_STATES = {
        MatchingAttempt.State.MATCHING_COMPLETED,
    }


    def get(self, request, token):
        # ── 1. Look up token ────────────────────────────────────────────────
        token_instance, already_used = consume_token(
            CoachActionToken.objects.select_related(
                'matching_attempt__matched_coach__user',
                'matching_attempt__participant',
            ),
            token,
        )

        if token_instance is None:
            return render(request, 'matching/response_invalid_token.html', status=200)

        ma = token_instance.matching_attempt
        coach = ma.matched_coach
        participant = ma.participant

        base_context = {
            'coach_name': coach.full_name,
            'participant_name': f"{participant.first_name} {participant.last_name}",
            'participant_first_name': participant.first_name,
        }

        # ── 2. Token already consumed ────────────────────────────────────────
        if already_used:
            return render(
                request,
                'matching/response_already_used.html',
                {**base_context},
            )

        # ── 3. MatchingAttempt already in a terminal state ────────────────────
        if ma.state in MatchingAttempt.TERMINAL_STATES:
            return render(
                request,
                'matching/response_already_used.html',
                {**base_context, 'previous_state': ma.get_state_display()},
            )

        
        services.create_matching_event(
            matching_attempt=ma,
            event_type=MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH,
            triggered_by=TriggeredByOptions.COACH,
            triggered_by_user=coach.user,
        )
        
        return render(
            request,
            'matching/coach_response_intro_call.html',
            {
                **base_context,
            },
        )

class FlowChartView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    template_name = 'matching/flow_chart.html'
    
    
class MatchingEventDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = MatchingEvent
    template_name = 'matching/matching_event_detail.html'
    context_object_name = 'matching_event'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['matching_attempt'] = context['matching_event'].matching_attempt
        # Pre-format payload values so templates can render dates/times correctly.
        payload = context['matching_event'].payload or {}
        formatted = []
        for k, v in payload.items():
            display = None
            # Try Django's dateparse to parse ISO datetime strings
            if isinstance(v, str):
                dt = dateparse.parse_datetime(v)
                if dt is not None:
                    try:
                        display = timezone.localtime(dt).strftime('%d.%m.%Y %H:%M:%S %Z')
                    except Exception:
                        display = dt.strftime('%d.%m.%Y %H:%M:%S')
            if display is None:
                # datetime/date/time objects
                if isinstance(v, (timezone.datetime,)):
                    try:
                        display = timezone.localtime(v).strftime('%d.%m.%Y %H:%M:%S %Z')
                    except Exception:
                        display = str(v)
                elif hasattr(v, 'isoformat') and not isinstance(v, (dict, list)):
                    display = str(v)
                elif isinstance(v, (dict, list)):
                    try:
                        display = json.dumps(v, ensure_ascii=False, indent=2)
                    except Exception:
                        display = str(v)
                else:
                    display = str(v)

            formatted.append((k, display))

        context['formatted_payload'] = formatted
        return context
    
class CancelMatchingView(LoginRequiredMixin, StaffRequiredMixin, View):
    """Transition a MatchingAttempt to CANCELLED.

    POST /matching/<pk>/cancel/
    """

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        services.cancel_matching(matching_attempt, triggered_by_user=request.user)
       
        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))
    
class ManualOverrideMatchingView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    """Manually set a matched coach on a MatchingAttempt, bypassing the normal flow. Used for exceptional cases where automation fails or manual intervention is desired.

    POST /matching/<pk>/manual_matching_override/
    """
    
    template_name = 'matching/manual_matching_override.html'
    
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        matching_attempt_pk = self.kwargs.get("matching_attempt_pk")
        matching_attempt = get_object_or_404(MatchingAttempt, pk=matching_attempt_pk)
        context["matching_attempt"] = matching_attempt
        context["available_coaches"] = Coach.objects.available().select_related('user').order_by('user__last_name', 'user__first_name')
        return context
    
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    
    def post(self, request, matching_attempt_pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=matching_attempt_pk)
        coach_id = request.POST.get("coach_id")
        coach = get_object_or_404(Coach, pk=coach_id)
        services.manually_match_participant_to_coach(matching_attempt, coach, triggered_by_user=request.user)
        return redirect(reverse("matching_attempt_detail", kwargs={"pk": matching_attempt_pk}))