from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse
from django.views.generic import DetailView, ListView, CreateView

from .models import MatchingAttempt, RequestToCoach


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
        context['email_logs'] = self.object.email_logs.all()
        return context
    

