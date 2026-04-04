from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import DetailView

from slack.models import SlackLog

class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts access to active staff and superusers only."""
    def test_func(self):
        return (self.request.user.is_active and self.request.user.is_staff) or self.request.user.is_superuser

class SlackLogDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = SlackLog
    template_name = 'slack/slack_log_detail.html'
    context_object_name = 'slack_log'