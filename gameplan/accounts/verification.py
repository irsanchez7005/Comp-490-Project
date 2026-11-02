import secrets
from datetime import timedelta

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import VerificationCode

CODE_TIME = timedelta(minutes=10)

def create_code(user, channel, purpose):
    """Create a fresh 6-digit verification code for a user.

    Any earlier unused codes for the same user, channel, and purpose are 
    marked as used first, so only the newest code is valid. The new code 
    expires after CODE_TIME (10 MINS).

    Args:
        user: The User the code belongs to.
        channel: A VerificationCode.Channel value (EMAIL or PHONE)
        purpose: A VerificationCode.Purpose value (SIGNUP or PASSWORD_RESET)

    Returns:
        The saved VerificationCode instance.
    """
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
    """Send a Verification Code to User's Email

    Purpose: Signup 
    """
    verification = create_code(user, VerificationCode.Channel.EMAIL, VerificationCode.Purpose.SIGNUP)
    body=render_to_string(
        "emails/verification_code.txt",
        {"user": user, "code": verification.code, "minutes":10},
    )
    send_mail("Your Verification Code", body, None, [user.email])

def send_password_reset_code(user):
    """Send a Verification Code to User's Email

    Purpose: Reset Password
    """
    verification = create_code(user, VerificationCode.Channel.EMAIL, VerificationCode.Purpose.PASSWORD_RESET)
    body=render_to_string(
        "emails/password_reset.txt",
        {"user": user, "code": verification.code, "minutes":10},
    )
    send_mail("Your Password-Reset Verification Code", body, None, [user.email])