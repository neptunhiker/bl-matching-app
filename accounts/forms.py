from django import forms
from django.contrib.auth.forms import AuthenticationForm, ReadOnlyPasswordHashField
from .models import User


class EmailAuthenticationForm(AuthenticationForm):
    """Login form using email instead of username."""

    error_messages = {
        'invalid_login': 'E-Mail oder Passwort falsch.',
        'inactive': 'Dieses Konto ist deaktiviert.',
    }

    username = forms.EmailField(
        label='E-Mail',
        widget=forms.EmailInput(attrs={
            'autofocus': True,
            'placeholder': 'deine@email.de',
            'class': (
                'w-full px-3 py-2 rounded-lg border border-neutral-300 '
                'focus:outline-none focus:ring-2 focus:ring-neutral-400 '
                'bg-white text-neutral-900 placeholder-neutral-400 text-sm'
            ),
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].label = 'Passwort'
        self.fields['password'].widget = forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'class': (
                'w-full px-3 py-2 rounded-lg border border-neutral-300 '
                'focus:outline-none focus:ring-2 focus:ring-neutral-400 '
                'bg-white text-neutral-900 placeholder-neutral-400 text-sm'
            ),
        })


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')

    def clean_password2(self):
        pw1 = self.cleaned_data.get('password1')
        pw2 = self.cleaned_data.get('password2')
        if pw1 and pw2 and pw1 != pw2:
            raise forms.ValidationError("Passwords don't match")
        return pw2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name', 'is_active', 'is_staff')

    def clean_password(self):
        return self.initial['password']
