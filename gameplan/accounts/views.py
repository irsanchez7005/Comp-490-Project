import secrets
import time
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from facility.models import Facility
from .forms import AccountRegisterForm
from django.contrib.auth.decorators import login_required
from .verification import send_email_code, send_password_reset_code
from .models import User, VerificationCode, Profile
from .forms import VerifyCodeForm, EmailLoginForm, ProfileForm,PasswordResetRequestForm, UserNameForm,EmailForm,ConfirmPasswordForm, DeleteAccountForm
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

    if request.method == "POST":
        form = VerifyCodeForm(request.POST)
        if form.is_valid():
            verification = (
                VerificationCode.objects
                .filter(user=user, channel=VerificationCode.Channel.EMAIL, purpose=VerificationCode.Purpose.SIGNUP, used=False)
                .order_by("-id")
                .first()
            )
            entered = form.cleaned_data['code']

            if (verification is None or verification.is_expired()
                    or not secrets.compare_digest(entered, verification.code)):
                form.add_error("code", "That code is invalid or has expired.")
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

    return render(request, "accounts/verify_email.html", {"form": form, "email": user.email})

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
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile_obj)
    return render(request, "accounts/profile.html", {"form": form})

PASSWORD_VERIFY_SECONDS=300

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
    form = ConfirmPasswordForm(request.user, request.POST)
    if request.method == "POST":
        user = request.user
        logout(request)
        messages.success(request,"Account deleted.")
        user.delete()
        return redirect('home')
    return render(request, "accounts/delete_confirm.html", {"form": form})

def passwordVerifyEmail(request):
    email = request.session.get("reset_email")
    if email is None:
        messages.error(request, "Please enter your email.")
        return redirect("password_reset")
    user =User.objects.filter(email=email).first()

    if request.method == "POST":
        form = VerifyCodeForm(request.POST)
        if form.is_valid():
            verification = (
                VerificationCode.objects
                .filter(user=user, channel=VerificationCode.Channel.EMAIL, purpose=VerificationCode.Purpose.PASSWORD_RESET, used=False)
                .order_by("-id")
                .first()
            )
            entered = form.cleaned_data['code']

            if (verification is None or verification.is_expired()
                    or not secrets.compare_digest(entered, verification.code)):
                form.add_error("code", "That code is invalid or has expired.")
            else:
                verification.used = True
                verification.save(update_fields=['used'])
                messages.success(request, "Code verified! Choose a new password.")
                request.session['reset_user_id'] = user.pk
                request.session['reset_verified'] =True
                return redirect("password_reset_confirm")
    else:
        form = VerifyCodeForm()

    return render(request, "accounts/password_reset_sent.html", {"form": form, "email": email})

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
            
