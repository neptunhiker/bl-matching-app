from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, CreateView, View

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
        return context

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

        if rtc.deadline is None or now <= rtc.deadline:
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
                'deadline': rtc.deadline,
            },
        )

