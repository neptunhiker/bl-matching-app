from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, CreateView, View

from profiles.models import Coach
from .models import CoachActionToken, MatchingAttempt, RequestToCoach
from .tokens import consume_token


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts the view to staff users only."""
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff


class MatchingAttemptCreateView(StaffRequiredMixin, CreateView):
    model = MatchingAttempt
    fields = ['participant']
    template_name = 'matching/matching_attempt_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('matching_attempt_detail', kwargs={'pk': self.object.pk})


class MatchingAttemptDetailView(LoginRequiredMixin, DetailView):
    model = MatchingAttempt
    template_name = 'matching/matching_attempt_detail.html'
    context_object_name = 'matching_attempt'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        matching_attempt = self.object
        # Collect all emails: directly on the matching attempt + all per-coach emails
        direct_emails = list(matching_attempt.email_logs.all().select_related('request_to_coach__coach'))
        coach_emails = []
        for req in matching_attempt.coach_requests.all().select_related('coach'):
            for email in req.email_logs.all().select_related('request_to_coach__coach'):
                coach_emails.append(email)
        # Merge and sort chronologically (newest first)
        all_emails = sorted(
            direct_emails + coach_emails,
            key=lambda e: e.sent_at,
            reverse=True,
        )
        context['all_emails'] = all_emails
        context['transitions'] = list(
            matching_attempt.transitions.select_related('triggered_by_user').order_by('created_at')
        )
        return context

class ToggleAutomationView(StaffRequiredMixin, View):
    """Enable or disable automation on a MatchingAttempt.

    POST /matching/<pk>/automation/
    Body: action=enable  or  action=disable
    """

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        action = request.POST.get("action")

        if action == "enable":
            matching_attempt.enable_automation()
        elif action == "disable":
            matching_attempt.disable_automation()

        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))


class CoachAutocompleteView(StaffRequiredMixin, View):
    """JSON endpoint: GET /matching/coaches/search/?q=<term>
    Returns up to 20 coaches whose name or email matches the query.
    """

    def get(self, request):
        q = request.GET.get("q", "").strip()
        qs = Coach.objects.select_related("user").order_by(
            "user__last_name", "user__first_name"
        )
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
        return render(request, "matching/request_to_coach_form.html", {
            "matching_attempt": matching_attempt,
            "next_priority": self._next_priority(matching_attempt),
        })

    def post(self, request, pk):
        matching_attempt = get_object_or_404(MatchingAttempt, pk=pk)
        coach_id = request.POST.get("coach_id", "").strip()
        max_requests = request.POST.get("max_number_of_requests", "3").strip()

        errors = {}

        coach = None
        if not coach_id:
            errors["coach"] = "Bitte einen Coach auswählen."
        else:
            try:
                coach = Coach.objects.get(pk=coach_id)
            except (Coach.DoesNotExist, ValueError):
                errors["coach"] = "Ungültiger Coach."

        try:
            max_requests = int(max_requests)
            if max_requests < 1:
                raise ValueError
        except (ValueError, TypeError):
            errors["max_number_of_requests"] = "Muss eine positive Zahl sein."

        if errors:
            return render(request, "matching/request_to_coach_form.html", {
                "matching_attempt": matching_attempt,
                "next_priority": self._next_priority(matching_attempt),
                "errors": errors,
                "posted_coach_name": request.POST.get("coach_name", ""),
                "posted_coach_id": coach_id,
                "posted_max_requests": request.POST.get("max_number_of_requests", "3"),
            })

        priority = self._next_priority(matching_attempt)
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            priority=priority,
            max_number_of_requests=max_requests,
        )
        return redirect(reverse("matching_attempt_detail", kwargs={"pk": pk}))


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
        context['email_logs'] = self.object.email_logs.order_by('-sent_at').select_related('request_to_coach__coach')
        context['transitions'] = list(
            self.object.transitions.select_related('triggered_by_user').order_by('created_at')
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
        RequestToCoach.Status.ACCEPTED_ON_TIME,
        RequestToCoach.Status.ACCEPTED_LATE,
        RequestToCoach.Status.REJECTED_ON_TIME,
        RequestToCoach.Status.REJECTED_LATE,
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
            return render(request, 'matching/coach_response_invalid.html', status=200)

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
            new_status = (
                RequestToCoach.Status.ACCEPTED_ON_TIME if is_accept
                else RequestToCoach.Status.REJECTED_ON_TIME
            )
        else:
            on_time = False
            new_status = (
                RequestToCoach.Status.ACCEPTED_LATE if is_accept
                else RequestToCoach.Status.REJECTED_LATE
            )

        rtc.status = new_status
        rtc.save(update_fields=['status'])

        return render(
            request,
            'matching/coach_response_success.html',
            {
                **base_context,
                'action': token_instance.action,        # 'accept' or 'decline'
                'is_accept': is_accept,
                'on_time': on_time,
                'deadline': rtc.deadline_at,
            },
        )

