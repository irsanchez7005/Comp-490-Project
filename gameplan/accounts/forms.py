from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Profile


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = User
        fields = ["username", "email", "phone"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["bio", "avatar", "city", "skill_level"]