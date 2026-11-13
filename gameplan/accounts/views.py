"""
Module: accounts/views.py
Programmer: Kelvin Jinn
Contributors: Matthew Messiha, Sumchhay Cheap
Last Updated: 11-02-2026
Description: Handles account pages: signup, email verification, email login,
        profile and edit profile, account settings, delete account, and password reset.
        Limits wrong verification code guesses to 3, then locks for 1 minute.
"""
import math
import secrets
import time
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from facility.models import Facility
from .forms import AccountRegisterForm
from django.contrib.auth.decorators import login_required
from .verification import send_email_code, send_password_reset_code
from .models import User, VerificationCode, Profile
from .forms import VerifyCodeForm, EmailLoginForm, ProfileForm,PasswordResetRequestForm, UserNameForm,EmailForm,ConfirmPasswordForm
from django.views.decorators.http import require_POST
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import SetPasswordForm

def home(request):
    return render(request, 'accounts/home.html')

def facility_list(request):
    facilities = Facility.objects.all()
    return render(request, "courses/courses-page.html", {"facilities": facilities})

def createAccount(request):
    if request.method == "POST":
        form = AccountRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.is_active=False
            user.save()
            send_email_code(user)
            request.session['pending_user_id'] = user.pk
            return redirect('verifyEmail')        
    else:
        form = AccountRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def verifyEmail(request):
    user_id = request.session.get("pending_user_id")
    if user_id is None:
        return redirect("createAccount")
    user =get_object_or_404(User, pk=user_id)
    lock_seconds = codeLockSeconds(user, VerificationCode.Purpose.SIGNUP)

    if request.method == "POST":
        form = VerifyCodeForm(request.POST)
        if lock_seconds:
            pass  # still locked: ignore the guess, the template shows the countdown
        elif form.is_valid():
            verification = (
                VerificationCode.objects
                .filter(user=user, channel=VerificationCode.Channel.EMAIL, purpose=VerificationCode.Purpose.SIGNUP, used=False)
                .order_by("-id")
                .first()
            )
            entered = form.cleaned_data['code']

            if verification is None or verification.is_expired():
                form.add_error("code", "That code is invalid or has expired.")
            elif not secrets.compare_digest(entered, verification.code):
                verification.attempts+=1
                if verification.attempts >= MAX_CODE_ATTEMPTS:
                    #lock for a minute, then allow 
                    verification.attempts =0
                    verification.locked_until = timezone.now() + timedelta(seconds=CODE_LOCK_SECONDS)
                    lock_seconds= CODE_LOCK_SECONDS
                else:
                    form.add_error("code", "That code is invalid or has expired.")
                verification.save(update_fields=["attempts", "locked_until"])
            else:
                verification.used = True
                verification.save(update_fields=['used'])
                user.is_active = True
                user.email_verified = True
                user.save(update_fields=['is_active', 'email_verified'])
                del request.session['pending_user_id']
                messages.success(request, "Email verified! You can now log in.")
                return redirect("login")
    else:
        form = VerifyCodeForm()

    return render(request, "accounts/verify_email.html", {"form": form, "email": user.email, "lock_seconds": lock_seconds})

class EmailLoginView(LoginView):
    template_name='accounts/login.html'
    authentication_form=EmailLoginForm

    def form_invalid(self, form):
        user =getattr(form, 'unverified_user', None)
        if user:
            send_email_code(user)
            self.request.session['pending_user_id'] = user.pk
            messages.info(self.request, "Please verify your email. We've sent you a new code.")
            return redirect('verifyEmail')
        return super().form_invalid(form)

@require_POST
def resendCode(request):
    user_id = request.session.get("pending_user_id")
    if user_id is None:
        return redirect("createAccount")
    user = get_object_or_404(User, pk=user_id)
    send_email_code(user)
    messages.info(request, "A new code has been sent.")
    return redirect("verifyEmail")

@login_required
def accountProfile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, "accounts/profile.html", {"profile": profile_obj})

@login_required
def editProfile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile_obj)
    return render(request, "accounts/edit_profile.html", {"form": form})

PASSWORD_VERIFY_SECONDS=300
MAX_CODE_ATTEMPTS= 3
CODE_LOCK_SECONDS = 60

def codeLockSeconds(user, purpose):
    """Return how many seconds are left before ``user`` can try a code again (0 = not locked).

    Checks every code for this purpose, not just the newest one, so
    requesting a new code with "Resend" doesn't skip the wait.
    """
    if user is None:
        return 0
    now = timezone.now()
    locked = (
        VerificationCode.objects
        .filter(user=user, purpose=purpose, locked_until__gt=now)
        .order_by("-locked_until")
        .first()
    )
    if locked is None:
        return 0
    return math.ceil((locked.locked_until - now).total_seconds())

@login_required
def accountSettings(request):
    user = request.user
    username_form = UserNameForm(instance=user, initial={"username": ""})
    email_form = EmailForm(instance=user, initial={"email": ""})
    confirm_form = ConfirmPasswordForm(user)
    new_password_form = SetPasswordForm(user)
    open_dialog = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "username":
            username_form = UserNameForm(request.POST, instance=user)
            if username_form.is_valid():
                username_form.save()
                messages.success(request, "Username updated.")
                return redirect("settings")
            open_dialog = "username-dialog"        

        elif action == "email":
            email_form = EmailForm(request.POST, instance=user)
            if email_form.is_valid():
                email_form.save()
                messages.success(request, "Email updated.")
                return redirect("settings")
            open_dialog = "email-dialog"

        elif action == "verify_password":
            confirm_form = ConfirmPasswordForm(user, request.POST)
            if confirm_form.is_valid():
                request.session["pw_verified_at"] = time.time()
                open_dialog = "new-password-dialog"
            else:
                open_dialog = "password-dialog"

        elif action == "set_password":
            verified_at = request.session.get("pw_verified_at")
            if verified_at is None or time.time() - verified_at > PASSWORD_VERIFY_SECONDS:
                request.session.pop("pw_verified_at", None)
                messages.error(request, "Please confirm your current password again.")
                return redirect("settings")
            new_password_form = SetPasswordForm(user, request.POST)
            if new_password_form.is_valid():
                user = new_password_form.save()
                update_session_auth_hash(request, user)
                request.session.pop("pw_verified_at", None)
                messages.success(request, "Password Changed.")
                return redirect("settings")
            open_dialog = "new-password-dialog"
    return render(request, "accounts/account_settings.html", {
        "username_form": username_form,
        "email_form": email_form,
        "confirm_form": confirm_form,
        "new_password_form": new_password_form,
        "open_dialog": open_dialog,
    })

@login_required
def deleteAccount(request):
    if request.method == "POST":
        form = ConfirmPasswordForm(request.user, request.POST)
        if form.is_valid():
            user = request.user
            logout(request)
            messages.success(request,"Account deleted.")
            user.delete()
            return redirect('home')
    else:
        form = ConfirmPasswordForm(request.user)
    return render(request, "accounts/delete_confirm.html", {"form": form})

def passwordVerifyEmail(request):
    email = request.session.get("reset_email") 
    if email is None:
        messages.error(request, "Please enter your email.")
        return redirect("password_reset")
    user =User.objects.filter(email=email).first()
    lock_seconds = codeLockSeconds(user, VerificationCode.Purpose.PASSWORD_RESET)

    if request.method == "POST":
        form = VerifyCodeForm(request.POST)
        if lock_seconds:
            pass  # still locked: ignore the guess, the template shows the countdown
        elif form.is_valid():
            verification = (
                VerificationCode.objects
                .filter(user=user, channel=VerificationCode.Channel.EMAIL, purpose=VerificationCode.Purpose.PASSWORD_RESET, used=False)
                .order_by("-id")
                .first()
            ) if user else None
            entered = form.cleaned_data['code']

            if verification is None or verification.is_expired():
                form.add_error("code", "That code is invalid or has expired.")
            elif not secrets.compare_digest(entered, verification.code):
                verification.attempts += 1
                if verification.attempts >= MAX_CODE_ATTEMPTS:
                    # lock for a minute, then allow another round of guesses
                    verification.attempts = 0
                    verification.locked_until = timezone.now() + timedelta(seconds=CODE_LOCK_SECONDS)
                    lock_seconds = CODE_LOCK_SECONDS
                else:
                    form.add_error("code", "That code is invalid or has expired.")
                verification.save(update_fields=["attempts", "locked_until"])
            else:
                verification.used = True
                verification.save(update_fields=['used'])
                messages.success(request, "Code verified! Choose a new password.")
                request.session['reset_user_id'] = user.pk
                request.session['reset_verified'] =True
                return redirect("password_reset_confirm")
    else:
        form = VerifyCodeForm()

    return render(request, "accounts/password_reset_sent.html", {
        "form": form,
        "email": email,
        "lock_seconds": lock_seconds,
    })

def passwordResetRequest(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].strip().lower()
            user = User.objects.filter(email=email).first()
            if user is not None:
                send_password_reset_code(user)
            request.session['reset_email']=email
            return redirect("password_reset_done")
    else:
        form=PasswordResetRequestForm()
    return render(request, "accounts/password_reset.html", {"form": form})

@require_POST
def resendPasswordCode(request):
    email = request.session.get("reset_email")
    if email is None:
        messages.error(request,"Email is empty. Enter your email to get the code.")
        return redirect("password_reset")
    user = User.objects.filter(email=email).first()
    messages.info(request, "A new code has been sent.")
    if user:
        send_password_reset_code(user)
    return redirect("password_reset_done")

def passwordResetConfirm(request):
    if not request.session.get("reset_verified"):
        return redirect("password_reset")
    user = get_object_or_404(User, pk=request.session['reset_user_id'])

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            request.session.pop("reset_email", None)
            request.session.pop("reset_user_id", None)
            request.session.pop("reset_verified", None)
            return redirect("password_reset_complete")
    else:
        form = SetPasswordForm(user)
    return render(request, "accounts/password_reset_confirm.html", {"form": form})
            
