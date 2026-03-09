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
    user = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label='Benutzer',
    )
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
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # set the user queryset
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields['user'].queryset = User.objects.order_by('last_name', 'first_name')
