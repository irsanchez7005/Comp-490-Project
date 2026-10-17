import secrets
from datetime import timedelta

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import VerificationCode

CODE_TIME = timedelta(minutes=10)

def create_code(user, channel, purpose):
    VerificationCode.objects.filter(user=user, channel=channel, purpose=purpose, used=False).update(used=True)

    code = f"{secrets.randbelow(1_000_000):06d}"
    return VerificationCode.objects.create(
        user=user,
        channel=channel,
        purpose=purpose,
        code=code,
        expires_at=timezone.now()+CODE_TIME,
    )

def send_email_code(user):
    verification = create_code(user, VerificationCode.Channel.EMAIL, VerificationCode.Purpose.SIGNUP)
    body=render_to_string(
        "emails/verification_code.txt",
        {"user": user, "code": verification.code, "minutes":10},
    )
    send_mail("Your Verification Code", body, None, [user.email])

def send_password_reset_code(user):
    verification = create_code(user, VerificationCode.Channel.EMAIL, VerificationCode.Purpose.PASSWORD_RESET)
    body=render_to_string(
        "emails/password_reset.txt",
        {"user": user, "code": verification.code, "minutes":10},
    )
    send_mail("Your Password-Reset Verification Code", body, None, [user.email])