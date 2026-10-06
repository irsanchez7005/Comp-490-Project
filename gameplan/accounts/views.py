import secrets

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import AccountRegisterForm, VerifyCodeForm
from django.contrib.auth.decorators import login_required
from .verification import send_email_code
from .models import User, VerificationCode
from django.views.decorators.http import require_POST

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
                .filter(user=user, channel=VerificationCode.Channel.EMAIL, used=False)
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
    return render(request, '') #user profile page
