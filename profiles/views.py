import os
import requests

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse, HttpResponseServerError
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy

from .forms import ParticipantForm, CoachForm
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
        user = self.request.user
        return (user.is_active and user.is_staff) or user.is_superuser


class ParticipantCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    model = Participant
    form_class = ParticipantForm
    template_name = 'profiles/participant_form.html'

    # Q&A question texts used for prefill
    _LANGUAGE_QUESTION = "Auf welcher Sprache möchtest du das Coaching machen?"
    _COACHING_FORMAT = "Wie möchtest du dein Coaching am liebsten machen?"
    _AVGS_QUESTION     = "Hast du schon einen AVGS Gutschein?"

    def get_initial(self):
        initial = super().get_initial()
        booking_pk = self.request.GET.get("booking")
        if not booking_pk:
            return initial

        from bookings.models import CalendlyBooking
        from .models import Language as LangModel

        try:
            booking = CalendlyBooking.objects.get(pk=booking_pk)
        except CalendlyBooking.DoesNotExist:
            return initial

        initial.update({
            "first_name": booking.invitee_first_name.lower().capitalize().strip(),
            "last_name":  booking.invitee_last_name.lower().capitalize().strip(),
            "email":      booking.invitee_email.strip(),
        })

        qa_map = {
            qa["question"].strip(): qa.get("answer", "")
            for qa in (booking.questions_and_answers or [])
            if "question" in qa
        }

        # Coaching format
        format_answer = qa_map.get(self._COACHING_FORMAT, "").strip()
        if format_answer:
            if format_answer.lower() in ["online", "präsenz", "hybrid"]:
                initial["coaching_format_online"] = format_answer.lower() == "online"
                initial["coaching_format_presence"] = format_answer.lower() == "präsenz"
                initial["coaching_format_hybrid"] = format_answer.lower() == "hybrid"
            
        
        # Language
        lang_answer = qa_map.get(self._LANGUAGE_QUESTION, "").strip()
        print(lang_answer)
        if lang_answer:
            matched = LangModel.objects.filter(name__iexact=lang_answer)
            if matched.exists():
                initial["languages"] = matched
        print(f"Prefilled languages: {initial.get('languages', [])}")

        # AVGS
        avgs_answer = qa_map.get(self._AVGS_QUESTION, "").strip().lower()
        if avgs_answer:
            initial["avgs_data_docs_available"] = avgs_answer.startswith("ja")

        return initial

    def get_success_url(self):
        return reverse_lazy('participant_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        booking_pk = self.request.GET.get("booking")
        if booking_pk:
            from bookings.models import CalendlyBooking
            try:
                booking = CalendlyBooking.objects.get(pk=booking_pk)
                self.object.calendly_booking = booking
                self.object.save(update_fields=["calendly_booking"])
            except CalendlyBooking.DoesNotExist:
                pass
        return response


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
        qs = super().get_queryset().prefetch_related('languages')

        # text search (name / email)
        q = self.request.GET.get('q')
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(email__icontains=q)
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
        return (user.is_active and user.is_staff) or user.is_superuser

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


class CoachDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Coach
    template_name = 'profiles/coach_confirm_delete.html'
    context_object_name = 'coach'
    success_url = reverse_lazy('coach_list') 
    
    


@login_required
def get_coaches(request):
    API_URL = "https://coaching-hub.beginnerluft.de/api/v1/coaches/"
    API_KEY = os.environ.get("COACHING_HUB_API_KEY")
    if not API_KEY:
        return HttpResponseServerError("API key not configured.")

    headers = {"Authorization": f"Api-Key {API_KEY}"}

    COACHING_HUB_API_URL = os.environ.get("COACHING_HUB_API_URL")
    COACHING_HUB_API_KEY = os.environ.get("COACHING_HUB_API_KEY")
    from django.http import JsonResponse, HttpResponseServerError

    if not API_URL:
        return HttpResponseServerError("API URL not configured.")
    if not API_KEY:
        return HttpResponseServerError("API key not configured.")

    headers = {
        "Authorization": f"Api-Key {API_KEY}",
    }

    try:
        response = requests.get(API_URL, headers=headers, timeout=10)
        response.raise_for_status()  # Raises an error for non-2xx responses
        coaches = response.json()
        return JsonResponse(coaches, safe=False)
    except requests.RequestException as e:
        return HttpResponseServerError(f"Error fetching coaches: {e}")