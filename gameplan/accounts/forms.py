from django import forms
from .models import Profile, User
from django.contrib.auth.forms import UserCreationForm

class AccountRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email']

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio', 'avatar', 'city', 'skill_level']
class VerifyCodeForm(forms.Form):
    code = forms.CharField(max_length=6, min_length=6, label="Verification Code")
