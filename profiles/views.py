from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView

from .forms import ParticipantForm, CoachForm
from .models import Participant, Coach

from matching.models import RequestToCoach


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts access to active staff users only."""
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'profiles/home.html'


# ---------------------------------------------------------------------------
# Participant CRUD
# ---------------------------------------------------------------------------

class ParticipantListView(StaffRequiredMixin, ListView):
    model = Participant
    template_name = 'profiles/participant_list.html'
    context_object_name = 'participants'
    paginate_by = 25


class ParticipantDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Participant
    template_name = 'profiles/participant_detail.html'
    context_object_name = 'participant'
    
    def test_func(self):
        """Allow access if user is staff or coach with a request for this participant."""
        coach = getattr(self.request.user, 'coach_profile', None)
        if coach is None:
            return self.request.user.is_staff or self.request.user.is_superuser
        else:
            return RequestToCoach.objects.filter(coach=coach, matching_attempt__participant=self.get_object()).exists()
    
    def get_template_names(self):
        user = self.request.user
        print(f"DEBUG: User {user} is_staff={user.is_staff} is_superuser={user.is_superuser}")
        if user.is_staff or user.is_superuser:
            return ["profiles/participant_detail.html"]
        return ["profiles/participant_detail_for_coach.html"]


class ParticipantCreateView(StaffRequiredMixin, CreateView):
    model = Participant
    form_class = ParticipantForm
    template_name = 'profiles/participant_form.html'

    def get_success_url(self):
        return reverse_lazy('participant_detail', kwargs={'pk': self.object.pk})


class ParticipantUpdateView(StaffRequiredMixin, UpdateView):
    model = Participant
    form_class = ParticipantForm
    template_name = 'profiles/participant_form.html'

    def get_success_url(self):
        return reverse_lazy('participant_detail', kwargs={'pk': self.object.pk})


class ParticipantDeleteView(StaffRequiredMixin, DeleteView):
    model = Participant
    template_name = 'profiles/participant_confirm_delete.html'
    context_object_name = 'participant'
    success_url = reverse_lazy('participant_list')


# ---------------------------------------------------------------------------
# Coach CRUD
# ---------------------------------------------------------------------------


class CoachListView(StaffRequiredMixin, ListView):
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


class CoachDetailView(StaffRequiredMixin, DetailView):
    model = Coach
    template_name = 'profiles/coach_detail.html'
    context_object_name = 'coach'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['Status'] = Coach.Status
        return context


class CoachCreateView(StaffRequiredMixin, CreateView):
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


class CoachUpdateView(StaffRequiredMixin, UpdateView):
    model = Coach
    form_class = CoachForm
    template_name = 'profiles/coach_form.html'

    def get_success_url(self):
        return reverse_lazy('coach_detail', kwargs={'pk': self.object.pk})


class CoachDeleteView(StaffRequiredMixin, DeleteView):
    model = Coach
    template_name = 'profiles/coach_confirm_delete.html'
    context_object_name = 'coach'
    success_url = reverse_lazy('coach_list')