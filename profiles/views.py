from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView

from .forms import ParticipantForm, CoachForm, CoachUpdateForm
from .models import Participant, Coach

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
        """Allow access if user is staff, or the coach is related to this participant.

        Staff and superusers have full access. Coaches have access if they are the
        matched coach for the participant or if they have a RequestToCoach for
        the participant.
        """
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return True

        coach = getattr(user, 'coach_profile', None)
        if not coach:
            return False

        participant = self.get_object()
        if MatchingAttempt.objects.filter(participant=participant, matched_coach=coach).exists():
            return True

        return RequestToCoach.objects.filter(
            coach=coach, matching_attempt__participant=participant
        ).exists()
    
    def get_template_names(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return ["profiles/participant_detail.html"]
        return ["profiles/participant_detail_for_coach.html"]


class ParticipantCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = Participant
    form_class = ParticipantForm
    template_name = 'profiles/participant_form.html'

    def get_success_url(self):
        return reverse_lazy('participant_detail', kwargs={'pk': self.object.pk})


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
    paginate_by = 25
    def get_queryset(self):
        qs = super().get_queryset().select_related('user').prefetch_related('languages')

        # text search (name / email)
        q = self.request.GET.get('q')
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(user__email__icontains=q)
            )

        # status filter
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        # (language filtering removed)

        # coaching formats
        if self.request.GET.get('format_online'):
            qs = qs.filter(coaching_format_online=True)
        if self.request.GET.get('format_presence'):
            qs = qs.filter(coaching_format_presence=True)
        if self.request.GET.get('format_hybrid'):
            qs = qs.filter(coaching_format_hybrid=True)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # expose status choices for the filter form
        context['statuses'] = Coach.Status.choices
        context['Status'] = Coach.Status

        # selected values for form population
        context['q'] = self.request.GET.get('q','')
        context['selected_status'] = self.request.GET.get('status','')
        context['selected_online'] = bool(self.request.GET.get('format_online'))
        context['selected_presence'] = bool(self.request.GET.get('format_presence'))
        context['selected_hybrid'] = bool(self.request.GET.get('format_hybrid'))

        # preserve other GET params for pagination links
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['params'] = params.urlencode()

        return context


class CoachDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Coach
    template_name = 'profiles/coach_detail.html'
    context_object_name = 'coach'

    def test_func(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return True
        coach = getattr(user, 'coach_profile', None)
        return coach is not None and coach == self.get_object()

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
    form_class = CoachUpdateForm
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