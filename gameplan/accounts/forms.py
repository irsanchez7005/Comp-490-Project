"""
Module: accounts/forms.py
Programmer: Kelvin Jinn
Last Updated: 11-02-2026
Description: Forms for the accounts app: registration, email login, profile editing,
        verification code entry, password reset request, and account settings
        (change username, change email, change password).
"""
from django import forms
from .models import Profile, User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

class AccountRegisterForm(UserCreationForm):
    """
    User SignUp Form 

    Fields: username, email, and two password fields inherited from UserCreationForm
    email is redeclared with (required=True) because Django's default user email is optional 
    """
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
    """Login form that uses email instead of username.

    The field is still named ``username`` because Django's AuthenticationForm always calls the login field ``username``
    ``error_messages`` replaces with ``email and password``; default was ``username and password`` 
    
    ``clean`` method:
        -It runs before the login check.
        -It saves the user as ``self.unverified_user`` and raises a ``unverified`` error 
        if the account was never verified.

    ``clean_username``:
        It's actually the email.
    """
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
    zip_code = forms.RegexField(
        regex=r'^[0-9]{5}(-[0-9]{4})?$', required=False, max_length=10,
        label="ZIP code", help_text="Use five digits or ZIP+4, such as 91306 or 91306-1234.",
        error_messages={'invalid': "Enter a valid ZIP code, such as 91306 or 91306-1234."},
        widget=forms.TextInput(attrs={'autocomplete': 'postal-code'}),
    )
    handicap = forms.DecimalField(
        required=False, max_digits=4, decimal_places=1, min_value=-10, max_value=54,
        label="Golf handicap", help_text="Enter a number from -10 to 54, with up to one decimal place.",
    )

    class Meta:
        model = Profile
        fields = ['avatar', 'cover_image', 'bio', 'city', 'zip_code', 'skill_level', 'handicap']
        labels = {'avatar': 'Profile picture', 'cover_image': 'Cover photo', 'skill_level': 'Golf skill level'}
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
            'city': forms.TextInput(attrs={'autocomplete': 'address-level2'}),
            'skill_level': forms.TextInput(attrs={'list': 'golf-skill-levels', 'placeholder': 'Choose or enter your skill level'}),
            'avatar': forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/gif,image/webp'}),
            'cover_image': forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/gif,image/webp'}),
        }
        help_texts = {
            'bio': 'Tell us about yourself (up to 500 characters).',
            'avatar': 'JPEG, PNG, GIF, or WebP. Maximum 5 MB.',
            'cover_image': 'JPEG, PNG, GIF, or WebP. Maximum 5 MB. A wide photo works best.',
        }

    def clean(self):
        cleaned_data = super().clean()
        for name in ('avatar', 'cover_image'):
            image = cleaned_data.get(name)
            if image and name in self.files:
                if image.size > 5 * 1024 * 1024:
                    self.add_error(name, "Choose an image no larger than 5 MB.")
                elif image.image.format not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
                    self.add_error(name, "Choose a JPEG, PNG, GIF, or WebP image.")
        return cleaned_data

class VerifyCodeForm(forms.Form):
    """
        Used for Both Signup and Password-Reset Codes.
    """
    code = forms.CharField(max_length=6, min_length=6, label="Verification Code")

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label='Email')

class UserNameForm(forms.ModelForm):
    """Username Change Form in Account Settings
    """
    class Meta:
        model = User
        fields = ['username']
        labels = {'username': 'New username'}
        widgets = {'username': forms.TextInput(attrs={'placeholder': 'Enter a new username'})}
    def clean_username(self):
        """check the case insensitive 
        ``.exclude(pk=self.instance.pk)`` skips the current user so it won't tell the own name is taken
        """
        #case-insensitive check
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

class EmailForm(forms.ModelForm):
    """Email Change Form in Account Settings
    """
    class Meta:
        model = User
        fields = ['email']
        labels = {'email': 'New email'}
        widgets = {'email': forms.EmailInput(attrs={'placeholder': 'Enter a new email'})}
    def clean_email(self):
        """check the case insensitive
        ``.exclude(pk=self.instance.pk)`` skips the current user so it won't tell the own email is taken
        """
        #case-insensitive check
        email = self.cleaned_data['email'].strip().lower()
        #check if there's same email in database
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

class ConfirmPasswordForm(forms.Form):
    """Ask for the user's current password and check it.

    Used for Delete Account, and changing password in Account Settings 
    """
    password = forms.CharField(widget=forms.PasswordInput, label="Current password")

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError("Your password was entered incorrectly.")
        return password
