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

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label='Email')

class UserNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username']
        labels = {'username': 'New username'}
        widgets = {'username': forms.TextInput(attrs={'placeholder': 'Enter a new username'})}
    def clean_username(self):
        #case-insensitive check
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

class EmailForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['email']
        labels = {'email': 'New email'}
        widgets = {'email': forms.EmailInput(attrs={'placeholder': 'Enter a new email'})}
    def clean_email(self):
        #case-insensitive check
        email = self.cleaned_data['email'].strip().lower()
        #check if there's same email in database
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

class ConfirmPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label="Current password")

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError("Your password was entered incorrectly.")
        return password

class DeleteAccountForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label="Confirm your password")