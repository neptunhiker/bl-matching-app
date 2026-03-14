from django import forms
from .models import Participant, Language, Coach


class ParticipantForm(forms.ModelForm):
    languages = forms.ModelMultipleChoiceField(
        queryset=Language.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Sprachen',
    )

    class Meta:
        model = Participant
        fields = [
            'first_name',
            'last_name',
            'email',
            'city',
            'languages',
            'coaching_format_online',
            'coaching_format_presence',
            'coaching_format_hybrid',
            'start_date',
            'background_information',
            'coaching_target',
            'avgs_data_docs_available',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'background_information': forms.Textarea(attrs={'rows': 4}),
            'coaching_target': forms.Textarea(attrs={'rows': 4}),
        }


class CoachForm(forms.ModelForm):

    languages = forms.ModelMultipleChoiceField(
        queryset=Language.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Sprachen',
    )

    class Meta:
        model = Coach
        fields = [
            'user',
            'city',
            'languages',
            'coaching_format_online',
            'coaching_format_presence',
            'coaching_format_hybrid',
            'status',
            'preferred_communication_channel',
            'slack_user_id',
        ]


