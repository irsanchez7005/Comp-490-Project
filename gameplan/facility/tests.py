from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import PaymentForm
from .models import Booking, Facility, TimeSlot
from .pricing import calculate_receipt
from .views import _create_paid_booking

VALID_PAYMENT = {
    "full_name": "Liam Smith",
    "credit_card_num": "1111-2222-3333-4444",
    "expiry": "12/99",
    "cvv": "987",
}


def create_user(name="golfer"):
    return get_user_model().objects.create_user(
        username=name, email=f"{name}@example.com", password="test-password"
    )


def create_slot(days_ahead=6, max_players=4):
    facility = Facility.objects.create(
        facility_name="Griffith Park",
        street_address="4730 Crystal Springs Dr",
        city="Los Angeles",
        zip_code="90027",
        sport_type="golf",
    )
    return TimeSlot.objects.create(
        facility=facility,
        date=timezone.localdate() + timedelta(days=days_ahead),
        start_time=time(9, 30),
        price_per_player=Decimal("45.00"),
        holes=18,
        max_players=max_players,
    )


class CalculateReceiptTests(SimpleTestCase):
    def test_matches_the_sample_receipt(self):
        receipt = calculate_receipt(Decimal("45.00"), 3)

        self.assertEqual(receipt.subtotal, Decimal("135.00"))
        self.assertEqual(receipt.discount, Decimal("0.00"))
        self.assertEqual(receipt.tax, Decimal("12.83"))
        self.assertEqual(receipt.total, Decimal("147.83"))

    def test_single_player(self):
        receipt = calculate_receipt(Decimal("20.00"), 1)

        self.assertEqual(receipt.subtotal, Decimal("20.00"))
        self.assertEqual(receipt.tax, Decimal("1.90"))
        self.assertEqual(receipt.total, Decimal("21.90"))


class PaymentFormTests(SimpleTestCase):
    def assert_rejected(self, field, value):
        form = PaymentForm({**VALID_PAYMENT, field: value})
        self.assertFalse(form.is_valid(), f"{field}={value!r} should be rejected")
        self.assertIn(field, form.errors)

    def test_accepts_valid_payment(self):
        self.assertTrue(PaymentForm(VALID_PAYMENT).is_valid())

    def test_card_number_separators_are_removed(self):
        for number in ("1111-2222-3333-4444", "1111 2222 3333 4444"):
            form = PaymentForm({**VALID_PAYMENT, "credit_card_num": number})
            self.assertTrue(form.is_valid())
            self.assertEqual(form.cleaned_data["credit_card_num"], "1111222233334444")

    def test_rejects_blank_name(self):
        self.assert_rejected("full_name", "   ")

    def test_rejects_bad_card_numbers(self):
        for number in ("", "123456789012", "12345678901234567890", "1111-2222-3333-abcd"):
            self.assert_rejected("credit_card_num", number)

    def test_rejects_malformed_expiry(self):
        for expiry in ("", "13/30", "00/30", "1/30", "12-30", "12/2030"):
            self.assert_rejected("expiry", expiry)

    def test_rejects_expired_month(self):
        last_month = timezone.localdate().replace(day=1) - timedelta(days=1)
        self.assert_rejected("expiry", f"{last_month:%m/%y}")

    def test_accepts_current_month(self):
        expiry = f"{timezone.localdate():%m/%y}"
        self.assertTrue(PaymentForm({**VALID_PAYMENT, "expiry": expiry}).is_valid())

    def test_rejects_bad_cvv(self):
        for cvv in ("", "12", "12345", "12a"):
            self.assert_rejected("cvv", cvv)


class CheckoutViewTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.slot = create_slot()
        self.facility_url = reverse("facility_detail", args=[self.slot.facility.pk])
        self.client.force_login(self.user)

    def get_checkout(self, slot_id, golfers):
        return self.client.get(reverse("checkout"), {"slot_id": slot_id, "golfers": golfers})

    def test_requires_login(self):
        self.client.logout()
        response = self.get_checkout(self.slot.pk, 3)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_shows_real_receipt(self):
        response = self.get_checkout(self.slot.pk, 3)
        self.assertEqual(response.status_code, 200)
        for text in ("Griffith Park", "18 holes", "3 players", "9:30 AM",
                     "135.00", "12.83", "147.83"):
            self.assertContains(response, text)

    def test_form_posts_and_carries_the_selection(self):
        response = self.get_checkout(self.slot.pk, 3)
        self.assertContains(response, f'action="{reverse("book_slot")}"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, f'name="slot_id" value="{self.slot.pk}"')
        self.assertContains(response, 'name="golfers" value="3"')

    def test_bad_slot_redirects_to_courses(self):
        for slot_id in ("abc", "", "999999"):
            response = self.get_checkout(slot_id, 1)
            self.assertRedirects(response, reverse("courses"))

    def test_bad_player_count_redirects_to_course(self):
        for golfers in ("abc", "", "0", "-1"):
            response = self.get_checkout(self.slot.pk, golfers)
            self.assertRedirects(response, self.facility_url)

    def test_past_slot_redirects_to_course(self):
        past_slot = create_slot(days_ahead=-1)
        response = self.get_checkout(past_slot.pk, 1)
        self.assertRedirects(
            response, reverse("facility_detail", args=[past_slot.facility.pk])
        )

    def test_too_few_spots_redirects_to_course(self):
        Booking.objects.create(slot=self.slot, user=self.user, num_players=3)
        response = self.get_checkout(self.slot.pk, 2)
        self.assertRedirects(response, self.facility_url)

    def test_cancelled_bookings_free_their_spots(self):
        Booking.objects.create(
            slot=self.slot, user=self.user, num_players=4,
            status=Booking.Status.CANCELLED,
        )
        self.assertEqual(self.get_checkout(self.slot.pk, 4).status_code, 200)


class BookingDialogTests(TestCase):
    def test_dialog_goes_to_checkout(self):
        slot = create_slot()
        self.client.force_login(create_user())
        response = self.client.get(reverse("facility_detail", args=[slot.facility.pk]))
        self.assertContains(
            response, f'action="{reverse("checkout")}" method="get"'
        )
        self.assertNotContains(response, 'name="tee_time"')


class BookSlotTests(TestCase):
    CARD_DIGITS = "1111222233334444"

    def setUp(self):
        self.user = create_user()
        self.slot = create_slot()
        self.client.force_login(self.user)

    def post_payment(self, golfers=3, **overrides):
        return self.client.post(reverse("book_slot"), {
            "slot_id": self.slot.pk,
            "golfers": golfers,
            **VALID_PAYMENT,
            **overrides,
        })

    def test_valid_payment_saves_booking_and_receipt(self):
        response = self.post_payment()

        booking = Booking.objects.get()
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.slot, self.slot)
        self.assertEqual(booking.num_players, 3)
        self.assertEqual(booking.subtotal, Decimal("135.00"))
        self.assertEqual(booking.tax, Decimal("12.83"))
        self.assertEqual(booking.total, Decimal("147.83"))
        self.assertEqual(booking.card_last4, "4444")
        self.assertRedirects(response, reverse("my_bookings"))

    def test_valid_payment_lands_on_my_bookings_with_alert_and_booking(self):
        response = self.client.post(reverse("book_slot"), {
            "slot_id": self.slot.pk,
            "golfers": 3,
            **VALID_PAYMENT,
        }, follow=True)

        self.assertRedirects(response, reverse("my_bookings"))
        self.assertContains(response, 'class="notice"')
        self.assertContains(response, "Your booking at Griffith Park is confirmed.")
        self.assertContains(response, 'class="booking-row')
        self.assertContains(response, "<h3>Griffith Park</h3>")

    def test_invalid_payment_creates_no_booking_and_shows_errors(self):
        response = self.post_payment(cvv="1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertContains(response, "Enter the 3 or 4 digit security code.")

    def test_invalid_payment_keeps_name_and_expiry_only(self):
        # This number differs from the input's placeholder, so finding it means a leak.
        response = self.post_payment(
            credit_card_num="4242 4242 4242 4242", expiry="13/99", cvv="987"
        )

        self.assertContains(response, 'value="Liam Smith"')
        self.assertContains(response, 'value="13/99"')
        self.assertNotContains(response, "4242 4242 4242 4242")
        self.assertNotContains(response, "4242424242424242")
        self.assertNotContains(response, 'value="987"')

    def test_full_slot_creates_no_booking(self):
        Booking.objects.create(slot=self.slot, user=self.user, num_players=4)

        response = self.post_payment(golfers=1)

        self.assertEqual(Booking.objects.count(), 1)
        self.assertRedirects(
            response, reverse("facility_detail", args=[self.slot.facility.pk])
        )

    def test_slot_filled_before_the_lock_creates_no_booking(self):
        Booking.objects.create(slot=self.slot, user=self.user, num_players=4)

        booking = _create_paid_booking(self.slot, self.user, 1, self.CARD_DIGITS)

        self.assertIsNone(booking)
        self.assertEqual(Booking.objects.count(), 1)

    def test_bad_selection_redirects_without_booking(self):
        response = self.client.post(reverse("book_slot"), {"slot_id": "abc", "golfers": 1})

        self.assertEqual(Booking.objects.count(), 0)
        self.assertRedirects(response, reverse("courses"))

    def test_requires_login(self):
        self.client.logout()

        response = self.post_payment()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Booking.objects.count(), 0)

    def test_rejects_get(self):
        self.assertEqual(self.client.get(reverse("book_slot")).status_code, 405)


class BookingConfirmationTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.booking = Booking.objects.create(
            slot=create_slot(),
            user=self.user,
            num_players=3,
            subtotal=Decimal("135.00"),
            tax=Decimal("12.83"),
            total=Decimal("147.83"),
            card_last4="4444",
        )
        self.url = reverse("booking_confirmation", args=[self.booking.pk])

    def test_owner_sees_receipt(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        for text in (f"Booking #{self.booking.pk}", "Griffith Park", "3 players",
                     "135.00", "12.83", "147.83", "4444"):
            self.assertContains(response, text)

    def test_other_user_gets_404(self):
        self.client.force_login(create_user("someone-else"))

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_booking_without_saved_amounts_hides_receipt(self):
        Booking.objects.filter(pk=self.booking.pk).update(
            subtotal=None, tax=None, total=None, card_last4=None
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Total")


class CancelBookingTests(TestCase):
    def test_cancelling_saves_the_status(self):
        user = create_user()
        booking = Booking.objects.create(slot=create_slot(), user=user, num_players=2)
        self.client.force_login(user)

        response = self.client.post(reverse("cancel_booking", args=[booking.pk]))

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertRedirects(response, reverse("my_bookings"))
