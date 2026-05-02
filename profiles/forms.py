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
            'end_date',
            'background_information',
            'coaching_target',
            'notes',
            'avgs_data_docs_available',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'background_information': forms.Textarea(attrs={'rows': 4}),
            'coaching_target': forms.Textarea(attrs={'rows': 4}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'Das Enddatum muss am oder nach dem Startdatum liegen.')

        return cleaned_data


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
            'first_name',
            'last_name',
            'email',
            'languages',
            'linkedin_url',
            'website_url',
            'preferred_coaching_location',
            'status',
            'status_notes',
            'maximum_capacity',
            'preferred_communication_channel',
            'slack_user_id',
        ]

