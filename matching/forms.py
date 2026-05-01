from django import forms

from profiles.models import Coach
from .models import MatchingNote, RequestToCoach


class MatchingNoteForm(forms.ModelForm):
    class Meta:
        model = MatchingNote
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Notiz hinzufügen …"}),
        }
        labels = {
            "body": "Notiz",
        }


class RequestToCoachUpdateForm(forms.ModelForm):
    class Meta:
        model = RequestToCoach
        fields = ['priority']
        error_messages = {
            'priority': {
                'invalid': "Muss eine ganze Zahl >= 1 sein.",
                'min_value': "Muss eine ganze Zahl >= 1 sein.",
            },
        }

    def clean_priority(self):
        priority = self.cleaned_data.get('priority')
        if priority is None or priority < 1:
            raise forms.ValidationError("Muss eine ganze Zahl >= 1 sein.")
        matching_attempt = self.instance.matching_attempt
        qs = matching_attempt.coach_requests.exclude(pk=self.instance.pk).filter(priority=priority)
        if qs.exists():
            raise forms.ValidationError("Diese Priorität ist bereits vergeben.")
        return priority


class RequestToCoachForm(forms.Form):
    coach_id = forms.CharField(
        required=False,
    )
    priority = forms.IntegerField(
        min_value=1,
        required=False,
        error_messages={
            'invalid': "Muss eine ganze Zahl >= 1 sein.",
            'min_value': "Muss eine ganze Zahl >= 1 sein.",
        },
    )
    ue = forms.IntegerField(
        min_value=1,
        error_messages={
            'invalid': "Muss eine positive Zahl sein.",
            'min_value': "Muss eine positive Zahl sein.",
            'required': "Muss eine positive Zahl sein.",
        },
    )

    def __init__(self, *args, matching_attempt=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.matching_attempt = matching_attempt
        self._coach = None

    @property
    def coach(self):
        """Returns the resolved Coach instance after successful validation."""
        return self._coach

    def clean_coach_id(self):
        coach_id = self.cleaned_data.get('coach_id', '').strip()
        if not coach_id:
            raise forms.ValidationError("Bitte einen Coach auswählen.")
        try:
            coach = Coach.objects.get(pk=coach_id)
        except (Coach.DoesNotExist, ValueError):
            raise forms.ValidationError("Ungültiger Coach.")
        if coach.status != Coach.Status.AVAILABLE:
            raise forms.ValidationError(
                f"Coach {coach.full_name} ist derzeit nicht verfügbar (Status: {coach.get_status_display()})."
            )
        if self.matching_attempt and self.matching_attempt.coach_requests.filter(coach=coach).exists():
            raise forms.ValidationError(
                f"Coach {coach.full_name} hat bereits eine Anfrage für dieses Matching."
            )
        self._coach = coach
        return coach_id

    def clean_priority(self):
        priority = self.cleaned_data.get('priority')
        if priority is None:
            return None
        if self.matching_attempt:
            existing = list(self.matching_attempt.coach_requests.values_list("priority", flat=True))
            if priority in existing:
                existing_sorted = ", ".join(str(p) for p in sorted(existing)) if existing else "keine"
                raise forms.ValidationError(
                    f"Diese Priorität ist bereits vergeben. Bestehende Prioritäten: {existing_sorted}"
                )
        return priority

    def clean_ue(self):
        ue = self.cleaned_data.get('ue')
        if ue is None:
            return ue
        if self.matching_attempt and ue > self.matching_attempt.ue:
            raise forms.ValidationError(
                f"Der Coach darf keinen Coaching-Auftrag erhalten, der mehr UE ({ue}) als die insgesamt genehmigten UE ({self.matching_attempt.ue}) hat."
            )
        return ue
