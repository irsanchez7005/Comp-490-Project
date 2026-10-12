from django import forms
from .models import Profile, User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

class AccountRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        #check if there's another same email in database
        if User.objects.filter(email__iexact=email).exists(): 
            raise forms.ValidationError("An account with this email already exists.")
        return email

class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'}),
    )
    
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': "Please enter a correct email and password.",
    }

    def clean(self):
        email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        if email and password:
            user=User.objects.filter(email=email).first()
            if (user and not user.is_active and 
                not user.email_verified and 
                user.check_password(password)):
                self.unverified_user = user
                raise forms.ValidationError(
                    "Please verify your email before logging in.", code="unverified"
                )
        return super().clean()

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio', 'avatar', 'city', 'skill_level']

class VerifyCodeForm(forms.Form):
    code = forms.CharField(max_length=6, min_length=6, label="Verification Code")
