from django import forms
from .models import User
from django.contrib.auth.forms import UserCreationForm

class AccountRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email']