from django.views.generic import DetailView, ListView

from .models import MatchingAttempt, RequestToCoach


class MatchingAttemptDetailView(DetailView):
    model = MatchingAttempt
    template_name = 'matching/matching_attempt_detail.html'
    context_object_name = 'matching_attempt'

class MatchingAttemptListView(ListView):
    model = MatchingAttempt
    template_name = 'matching/matchings.html'
    context_object_name = 'matching_attempts'
    
class RequestToCoachDetailView(DetailView):
    model = RequestToCoach
    template_name = 'matching/request_to_coach_detail.html'
    context_object_name = 'request_to_coach'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['email_logs'] = self.object.email_logs.all()
        return context
    

