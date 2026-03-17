import os

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, CreateView, View, UpdateView, DeleteView, TemplateView
from django.contrib import messages
from django.db import IntegrityError
from django.utils.html import format_html
from urllib3 import request
from urllib.parse import urlparse


from profiles.models import Coach
from .models import CoachActionToken, MatchingAttempt, RequestToCoach, MatchingAttemptEvent, RequestToCoachEvent
from .tokens import consume_token
from matching import services


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts the view to staff users only."""
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff


class MatchingAttemptCreateView(StaffRequiredMixin, CreateView):
    model = MatchingAttempt
    fields = ['participant', 'ue', ]
    template_name = 'matching/matching_attempt_form.html'

    def form_valid(self, form):
        participant = form.cleaned_data["participant"]
        ue = form.cleaned_data["ue"]

        if ue < 1:
            messages.error(self.request, "Die Anzahl der Unterrichtseinheiten muss mindestens 1 sein.")
            return self.form_invalid(form)
        
        # Prevent DB integrity error by validating existence first and provide link.
        active_ma = MatchingAttempt.objects.filter(
            participant=participant,
            status__in=[
                MatchingAttempt.Status.IN_PREPARATION,
                MatchingAttempt.Status.READY_FOR_MATCHING,
                MatchingAttempt.Status.MATCHING_ONGOING,
            ],
        ).order_by("-created_at").first()

        if active_ma is not None:
            messages.error(
                self.request,
                format_html(
                    "Konnte Matching nicht erstellen: es existiert bereits ein <a href='{}' style='text-decoration:underline'>aktives Matching</a> für {}.",
                    active_ma.get_absolute_url(),
                    participant,
                ),
            )
            return self.form_invalid(form)

        # Race conditions may still cause an IntegrityError; handle gracefully.
        try:
            self.object = services.create_matching_attempt(
                participant=participant,
                ue=ue,
                created_by=self.request.user,
            )
        except IntegrityError:
            # In case of a race, try to find the active matching to link to.
            conflicting = MatchingAttempt.objects.filter(
                participant=participant,
                status__in=[
                    MatchingAttempt.Status.IN_PREPARATION,
                    MatchingAttempt.Status.READY_FOR_MATCHING,
                    MatchingAttempt.Status.MATCHING_ONGOING,
                ],
            ).order_by("-created_at").first()

            if conflicting is not None:
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
                    f"Konnte Matching nicht erstellen: bereits ein aktives Matching vorhanden."
                )
            return self.form_invalid(form)

        return redirect(self.object.get_absolute_url())
    
       
        

    def get_success_url(self):
        return reverse('matching_attempt_detail', kwargs={'pk': self.object.pk})


class MatchingAttemptDetailView(LoginRequiredMixin, DetailView):
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
        context['transitions'] = list(
            matching_attempt.transitions.order_by('-created_at')
        )
        events = [matching_attempt.events.order_by('created_at')]
        
        for rtc in matching_attempt.coach_requests.all():
            rtc_events = rtc.events.order_by('created_at').select_related('request__coach')
            events.append(rtc_events)
        
        ordered_events = sorted(
            [event for sublist in events for event in sublist],  # flatten list of querysets
            reverse=True,
            key=lambda e: e.created_at,
        )
        context['events'] = ordered_events
            

        return context

class StartMatchingView(StaffRequiredMixin, View):
    """Transition a MatchingAttempt from DRAFT → READY_FOR_MATCHING.

    POST /matching/<pk>/start/
    """

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        matching_attempt.start_matching(
            triggered_by_user=request.user,
        )
        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))


class ToggleAutomationView(StaffRequiredMixin, View):
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


class CoachAutocompleteView(StaffRequiredMixin, View):
    """JSON endpoint: GET /matching/coaches/search/?q=<term>
    Returns up to 20 coaches whose name or email matches the query.
    """

    def get(self, request):
        q = request.GET.get("q", "").strip()
        qs = Coach.objects.available().select_related('user')
        if q:
            qs = qs.filter(
                Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
                | Q(user__email__icontains=q)
            )
        results = [
            {
                "id": str(coach.pk),
                "name": coach.full_name,
                "email": coach.email,
                "status": coach.get_status_display(),
            }
            for coach in qs[:20]
        ]
        return JsonResponse({"results": results})


class RequestToCoachCreateView(StaffRequiredMixin, View):
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
        if coach.status != Coach.Status.AVAILABLE:
            errors["coach"] = f"Coach {coach.full_name} ist derzeit nicht verfügbar (Status: {coach.get_status_display()})."

        if "coach" not in errors:
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
            except (ValueError, TypeError):
                errors["ue"] = "Muss eine positive Zahl sein."
            
            try:
                if ue > matching_attempt.ue:
                    raise ValueError
            except (ValueError):
                errors["ue"] = f"Der Coach darf keinen Coaching-Auftrag erhalten, der mehr UE ({ue}) als die insgesamt genehmigten UE ({matching_attempt.ue}) hat."

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
            triggered_by=RequestToCoachEvent.TriggeredBy.STAFF,
            triggered_by_user=request.user,
        )

        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))


class RequestToCoachUpdateView(StaffRequiredMixin, UpdateView):
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


class RequestToCoachDeleteView(StaffRequiredMixin, DeleteView):
    model = RequestToCoach
    template_name = 'matching/request_to_coach_confirm_delete.html'

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


class MatchingAttemptListView(LoginRequiredMixin, ListView):
    model = MatchingAttempt
    template_name = 'matching/matchings.html'
    context_object_name = 'matching_attempts'
    
class RequestToCoachDetailView(LoginRequiredMixin, DetailView):
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

        context['transitions'] = list(
            self.object.transitions.order_by('-created_at')
        )
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
    2. Token already used (used_at set) → coach_response_already_used.html
    3. RequestToCoach already resolved  → coach_response_already_used.html
       (coach replied via a different email's token — e.g. accepted email 1,
       then clicked the decline link in the reminder email)
    4. Determine on-time vs. late:
         now <= deadline  → ACCEPTED_ON_TIME / REJECTED_ON_TIME
         now >  deadline  → ACCEPTED_LATE    / REJECTED_LATE
         no deadline set  → treat as on-time (safe fallback)
    5. Save new status and render coach_response_success.html
    """

    # States that mean the coach has already given a definitive answer.
    TERMINAL_STATUSES = {
        RequestToCoach.Status.ACCEPTED_MATCHING,
        RequestToCoach.Status.REJECTED_MATCHING,
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
            return render(request, 'matching/coach_response_invalid_token.html', status=200)

        rtc = token_instance.request_to_coach
        coach = rtc.coach
        participant = rtc.matching_attempt.participant

        base_context = {
            'coach_name': coach.full_name,
            'participant_name': f"{participant.first_name} {participant.last_name}",
        }

        # ── 2. Token already consumed ────────────────────────────────────────
        if already_used:
            return render(
                request,
                'matching/coach_response_already_used.html',
                {**base_context, 'previous_status': rtc.get_status_display()},
            )

        # ── 3. RequestToCoach already in a terminal state ────────────────────
        if rtc.status in self.TERMINAL_STATUSES:
            return render(
                request,
                'matching/coach_response_already_used.html',
                {**base_context, 'previous_status': rtc.get_status_display()},
            )

        # ── 4 & 5. Determine timing and update status ────────────────────────
        now = timezone.now()
        is_accept = token_instance.action == CoachActionToken.Action.ACCEPT

        if rtc.deadline_at is None or now <= rtc.deadline_at:
            on_time = True

            if is_accept:
                
                ma = rtc.matching_attempt.transition_to(
                    MatchingAttempt.Status.MATCHING_CONFIRMED,
                )
                
                ma.matched_coach = rtc.coach
                ma.save(update_fields=['status', 'matched_coach'])
                
                ma = rtc.matching_attempt.transition_to(
                    MatchingAttempt.Status.READY_FOR_INTRO_CALL,
                )
                
                rtc = rtc.transition_to(
                    RequestToCoach.Status.ACCEPTED_MATCHING,
                )

                RequestToCoachEvent.objects.create(
                    request=rtc,
                    event_type=RequestToCoachEvent.EventType.MATCHING_ACCEPTED,
                    triggered_by=RequestToCoachEvent.TriggeredBy.COACH,
                    triggered_by_user=coach.user,
                )
            else:
                # Decline
                rtc = rtc.transition_to(
                    RequestToCoach.Status.REJECTED_MATCHING,
                )

                RequestToCoachEvent.objects.create(
                    request=rtc,
                    event_type=RequestToCoachEvent.EventType.MATCHING_REJECTED,
                    triggered_by=RequestToCoachEvent.TriggeredBy.COACH,
                    triggered_by_user=coach.user,
                )
        else:
            on_time = False

        return render(
            request,
            'matching/coach_response_success.html',
            {
                **base_context,
                'action': token_instance.action, # 'accept' or 'decline'
                'is_accept': is_accept,
                'on_time': on_time,
                'deadline': rtc.deadline_at,
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
    TERMINAL_STATUSES = {
        MatchingAttempt.Status.MATCHING_COMPLETED,
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
            return render(request, 'matching/coach_response_invalid_token.html', status=200)

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
                'matching/coach_response_already_used.html',
                {**base_context},
            )

        # ── 3. RequestToCoach already in a terminal state ────────────────────
        if ma.status in self.TERMINAL_STATUSES:
            return render(
                request,
                'matching/coach_response_already_used.html',
                {**base_context, 'previous_status': ma.get_status_display()},
            )

        # ── 4 & 5. Determine timing and update status ────────────────────────
        ma = ma.transition_to(
            MatchingAttempt.Status.INTRO_CALL_CONFIRMED,
        )
        
        ma = ma.transition_to(
            MatchingAttempt.Status.READY_FOR_START_EMAIL,
        )
        
        MatchingAttemptEvent.objects.create(
            matching_attempt=ma,
            event_type=MatchingAttemptEvent.EventType.INTRO_CALL_CONFIRMED,
            triggered_by=MatchingAttemptEvent.TriggeredBy.COACH,
            triggered_by_user=coach.user,
        )

        return render(
            request,
            'matching/coach_response_intro_call.html',
            {
                **base_context,
            },
        )

class FlowChartView(LoginRequiredMixin, TemplateView):
    template_name = 'matching/flow_chart.html'