"""Checks the format of card details for the simulated checkout."""
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

CARD_SEPARATORS = re.compile(r"[\s-]")
CARD_NUMBER = re.compile(r"[0-9]{13,19}")
EXPIRY = re.compile(r"(0[1-9]|1[0-2])/([0-9]{2})")
CVV = re.compile(r"[0-9]{3,4}")
EXPIRY_CENTURY = 2000


class PaymentForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    credit_card_num = forms.CharField()
    expiry = forms.CharField()
    cvv = forms.CharField()

    def clean_credit_card_num(self):
        digits = CARD_SEPARATORS.sub("", self.cleaned_data["credit_card_num"])
        if not CARD_NUMBER.fullmatch(digits):
            raise ValidationError("Enter a card number with 13 to 19 digits.")
        return digits

    def clean_expiry(self):
        expiry = self.cleaned_data["expiry"]
        match = EXPIRY.fullmatch(expiry)
        if not match:
            raise ValidationError("Enter the expiry date as MM/YY.")
        expires = (EXPIRY_CENTURY + int(match[2]), int(match[1]))
        today = timezone.localdate()
        if expires < (today.year, today.month):
            raise ValidationError("This card has expired.")
        return expiry

    def clean_cvv(self):
        cvv = self.cleaned_data["cvv"]
        if not CVV.fullmatch(cvv):
            raise ValidationError("Enter the 3 or 4 digit security code.")
        return cvv
