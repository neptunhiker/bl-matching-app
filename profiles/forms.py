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
            'background_information',
            'coaching_target',
        ]
        widgets = {
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
            'city',
            'languages',
            'coaching_format_online',
            'coaching_format_presence',
            'coaching_format_hybrid',
            'status',
            'preferred_communication_channel',
        ]


