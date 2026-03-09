from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView

from .forms import ParticipantForm, CoachForm
from .models import Participant, Coach


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


class ParticipantDetailView(StaffRequiredMixin, DetailView):
    model = Participant
    template_name = 'profiles/participant_detail.html'
    context_object_name = 'participant'


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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['Status'] = Coach.Status
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