from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView

from slack.models import SlackLog


class SlackLogDetailView(LoginRequiredMixin, DetailView):
    model = SlackLog
    template_name = 'slack/slack_log_detail.html'
    context_object_name = 'slack_log'