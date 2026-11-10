from datetime import datetime, time, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.html import parse_html
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


@override_settings(TIME_ZONE="UTC")
class CourseFilterTests(TestCase):
    now = datetime(2030, 6, 10, 10, 0, tzinfo=datetime_timezone.utc)
    tomorrow = now.date() + timedelta(days=1)

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.park = Facility.objects.create(
            facility_name="Griffith Park", street_address="1 Park Drive",
            city="Los Angeles", zip_code="90027-1234", sport_type="golf", rating=4.5,
        )
        cls.valley = Facility.objects.create(
            facility_name="Valley Golf", street_address="2 Valley Road",
            city="Northridge", zip_code="91306", sport_type="golf", rating=3.5,
        )
        cls.premium = Facility.objects.create(
            facility_name="Canyon Golf", street_address="3 Canyon Road",
            city="Los Angeles", zip_code="90027", sport_type="golf", rating=4.8,
        )
        cls.empty = Facility.objects.create(
            facility_name="Unrated Club", street_address="4 Club Road",
            city="Pasadena", zip_code="91101", sport_type="golf", rating=None,
        )
        cls.morning = cls.add_slot(cls.park, time(9), "80.00", 18)
        cls.afternoon = cls.add_slot(cls.park, time(12), "40.00", 9)
        cls.evening = cls.add_slot(cls.valley, time(17), "60.00", 9)
        cls.expensive = cls.add_slot(cls.premium, time(7), "250.00", 18)

    @classmethod
    def add_slot(cls, facility, start_time, price="50.00", holes=18, date=None, max_players=4):
        return TimeSlot.objects.create(
            facility=facility, date=date or cls.tomorrow, start_time=start_time,
            price_per_player=Decimal(price), holes=holes, max_players=max_players,
        )

    def setUp(self):
        self.enterContext(patch("django.utils.timezone.now", return_value=self.now))

    def search(self, **params):
        response = self.client.get(reverse("courses"), params)
        self.assertEqual(response.status_code, 200)
        return response

    def assert_courses(self, response, *facilities):
        self.assertCountEqual(
            [f.pk for f in response.context["facilities"]], [f.pk for f in facilities],
        )

    def test_default_directory_includes_courses_without_slots(self):
        response = self.search()
        self.assert_courses(response, self.park, self.valley, self.premium, self.empty)
        self.assertFalse(response.context["filter_form"].cleaned_data["available"])
        self.assertContains(response, "4 matching courses")
        self.assertContains(response, "No upcoming prices")
        self.assertNotContains(response, "coming soon")

    def test_courses_markup_is_valid_with_filters_and_errors(self):
        for params in ({}, {"q": "Park", "available": "1"}, {"min_price": "100", "max_price": "50"}):
            with self.subTest(params=params):
                response = self.search(**params)
                content = response.content.decode().split("<main>", 1)[1].split("</main>", 1)[0]
                parse_html(content)
                self.assertContains(response, 'aria-controls="course-filter-sidebar"')
                self.assertContains(response, 'id="course-filter-sidebar"')

    def test_course_name_is_partial_case_insensitive_and_trimmed(self):
        response = self.search(course_name="  gRiFfItH  ")
        self.assert_courses(response, self.park)
        self.assertEqual(response.context["filter_form"].cleaned_data["course_name"], "gRiFfItH")
        self.assertContains(response, 'value="  gRiFfItH  "')

    def test_city_search(self):
        self.assert_courses(self.search(location="  aNgEl  "), self.park, self.premium)

    def test_zip_search(self):
        self.assert_courses(self.search(location="91306"), self.valley)

    def test_zip_plus_four(self):
        self.assert_courses(self.search(location="90027"), self.park, self.premium)
        self.assert_courses(self.search(location="90027-1234"), self.park)

    def test_name_and_location_are_independent(self):
        self.assert_courses(self.search(course_name="golf", location="los angeles"), self.premium)
        self.assert_courses(self.search(course_name="Griffith", location="Northridge"))

    def test_date_filters_matching_slots_and_preserves_value(self):
        later = self.tomorrow + timedelta(days=2)
        self.add_slot(self.empty, time(8), date=later)
        response = self.search(date=later.isoformat())
        self.assert_courses(response, self.empty)
        self.assertContains(response, f'value="{later.isoformat()}"')

    def test_no_date_does_not_limit_to_today(self):
        self.assert_courses(self.search(available="1"), self.park, self.valley, self.premium)

    def test_past_date_and_elapsed_times_do_not_qualify(self):
        yesterday = self.now.date() - timedelta(days=1)
        self.add_slot(self.empty, time(8), "1.00", date=yesterday)
        self.add_slot(self.empty, time(9, 59), "2.00", date=self.now.date())
        self.add_slot(self.empty, time(10), "3.00", date=self.now.date())
        self.assert_courses(self.search(date=yesterday.isoformat()))
        self.assert_courses(self.search(date=self.now.date().isoformat()))
        self.assert_courses(self.search(available="1"), self.park, self.valley, self.premium)
        self.add_slot(self.empty, time(10, 1), "25.00", date=self.now.date())
        response = self.search(date=self.now.date().isoformat(), available="1")
        self.assert_courses(response, self.empty)
        self.assertEqual(response.context["facilities"][0].from_price, Decimal("25.00"))

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_availability_uses_the_configured_local_time(self):
        self.add_slot(self.empty, time(2, 59), date=self.now.date())
        self.add_slot(self.empty, time(3, 1), date=self.now.date())
        response = self.search(date=self.now.date().isoformat(), available="1")
        self.assert_courses(response, self.empty)
        self.assertEqual(response.context["facilities"][0].slot_count, 1)

    def test_time_periods(self):
        for period, expected in (
            ("morning", (self.park, self.premium)),
            ("afternoon", (self.park,)),
            ("evening", (self.valley,)),
        ):
            with self.subTest(period=period):
                response = self.search(tee_time=period, date=self.tomorrow.isoformat())
                self.assert_courses(response, *expected)
                self.assertEqual(response.context["filter_form"].cleaned_data["tee_time"], period)

    def test_time_period_boundaries_do_not_overlap(self):
        cases = [
            (time(4, 59), None), (time(5), "morning"), (time(11, 59), "morning"),
            (time(12), "afternoon"), (time(16, 59), "afternoon"),
            (time(17), "evening"), (time(23, 59), "evening"),
        ]
        slot = self.add_slot(self.empty, time(1))
        for start, expected in cases:
            slot.start_time = start
            slot.save(update_fields=["start_time"])
            for period in ("morning", "afternoon", "evening"):
                with self.subTest(start=start, period=period):
                    response = self.search(course_name="Unrated", tee_time=period)
                    self.assert_courses(response, *((self.empty,) if period == expected else ()))

    def test_price_range_uses_per_player_prices(self):
        response = self.search(min_price="50", max_price="80", golfers="4")
        self.assert_courses(response, self.park, self.valley)
        prices = {f.pk: f.from_price for f in response.context["facilities"]}
        self.assertEqual(prices[self.park.pk], Decimal("80.00"))
        self.assertEqual(prices[self.valley.pk], Decimal("60.00"))
        self.assertContains(response, 'value="50"')
        self.assertContains(response, 'value="80"')

    def test_top_price_value_is_unlimited(self):
        self.assert_courses(self.search(max_price="200"), self.park, self.valley, self.premium, self.empty)
        self.assert_courses(self.search(min_price="220", max_price="200"), self.premium)
        self.assert_courses(self.search(max_price="199"), self.park, self.valley)

    def test_zero_price_is_displayed_and_filterable(self):
        self.add_slot(self.empty, time(8), "0.00")
        response = self.search(max_price="0")
        self.assert_courses(response, self.empty)
        self.assertContains(response, "$0.00")

    def test_golfers_use_remaining_capacity(self):
        Booking.objects.create(slot=self.morning, user=self.user, num_players=2)
        params = {"course_name": "Griffith", "tee_time": "morning"}
        self.assert_courses(self.search(**params, golfers="2"), self.park)
        self.assert_courses(self.search(**params, golfers="3"))

    def test_multiple_confirmed_bookings_are_added(self):
        Booking.objects.create(slot=self.morning, user=self.user, num_players=1)
        Booking.objects.create(slot=self.morning, user=self.user, num_players=2)
        self.assert_courses(self.search(course_name="Griffith", holes="18", golfers="2"))
        self.assert_courses(self.search(course_name="Griffith", holes="18", golfers="1"), self.park)

    def test_cancelling_a_booking_restores_availability(self):
        booking = Booking.objects.create(slot=self.expensive, user=self.user, num_players=4)
        self.assert_courses(self.search(course_name="Canyon", available="1"))
        self.client.force_login(self.user)
        self.client.post(reverse("cancel_booking", args=[booking.pk]))
        self.assert_courses(self.search(course_name="Canyon", golfers="4"), self.premium)

    def test_cancelled_bookings_do_not_count(self):
        Booking.objects.create(
            slot=self.morning, user=self.user, num_players=4, status=Booking.Status.CANCELLED,
        )
        self.assert_courses(self.search(course_name="Griffith", holes="18", golfers="4"), self.park)

    def test_holes_and_missing_holes(self):
        self.add_slot(self.empty, time(8), holes=None)
        self.assert_courses(self.search(holes="9"), self.park, self.valley)
        self.assert_courses(self.search(holes="18"), self.park, self.premium)
        self.assert_courses(self.search(available="1"), self.park, self.valley, self.premium, self.empty)

    def test_minimum_rating_excludes_unrated_courses(self):
        for rating, expected in (("3", (self.park, self.valley, self.premium)),
                                 ("4", (self.park, self.premium)),
                                 ("4.5", (self.park, self.premium))):
            with self.subTest(rating=rating):
                self.assert_courses(self.search(rating=rating), *expected)

    def test_available_only_hides_full_and_empty_courses(self):
        Booking.objects.create(slot=self.expensive, user=self.user, num_players=4)
        self.assert_courses(self.search(available="1"), self.park, self.valley)
        self.assert_courses(self.search(), self.park, self.valley, self.premium, self.empty)
        self.assert_courses(self.search(course_name="Canyon", holes="18"), self.premium)

    def test_available_count_excludes_fully_booked_slots(self):
        Booking.objects.create(slot=self.morning, user=self.user, num_players=4)
        response = self.search(course_name="Griffith")
        course = response.context["facilities"][0]
        self.assertEqual(course.slot_count, 2)
        self.assertEqual(course.available_count, 1)
        self.assertContains(response, "1 tee time with space")

    def test_price_sort_and_missing_prices_last(self):
        response = self.search(sort="price")
        self.assertEqual(list(response.context["facilities"]), [self.park, self.valley, self.premium, self.empty])

    def test_rating_sort_and_unrated_last(self):
        response = self.search(sort="rating")
        self.assertEqual(list(response.context["facilities"]), [self.premium, self.park, self.valley, self.empty])

    def test_earliest_sort_uses_date_then_time_from_same_slot(self):
        self.add_slot(self.park, time(5), date=self.tomorrow + timedelta(days=1))
        response = self.search(sort="earliest")
        self.assertEqual(list(response.context["facilities"]), [self.premium, self.park, self.valley, self.empty])
        park = response.context["facilities"][1]
        self.assertEqual(park.earliest_date, self.tomorrow)
        self.assertEqual(park.earliest_time, time(9))

    def test_name_sort_is_case_insensitive(self):
        self.valley.facility_name = "apple golf"
        self.valley.save(update_fields=["facility_name"])
        response = self.search(sort="name")
        self.assertEqual(list(response.context["facilities"]), [self.valley, self.premium, self.park, self.empty])

    def test_sort_ties_are_stable(self):
        Facility.objects.update(rating=4)
        self.assertEqual(list(self.search(sort="rating").context["facilities"]),
                         [self.park, self.valley, self.premium, self.empty])

    def test_sort_and_display_use_matching_prices(self):
        self.add_slot(self.valley, time(8), "70.00", 18)
        response = self.search(holes="18", sort="price")
        self.assertEqual(list(response.context["facilities"]), [self.valley, self.park, self.premium])
        self.assertEqual(response.context["facilities"][1].from_price, Decimal("80.00"))
        self.assertNotContains(response, "$40.00")

    def test_available_sort_does_not_use_full_or_past_slots(self):
        Booking.objects.create(slot=self.afternoon, user=self.user, num_players=4)
        self.add_slot(self.park, time(8), "1.00", date=self.now.date() - timedelta(days=1))
        response = self.search(available="1", sort="price")
        self.assertEqual(list(response.context["facilities"]), [self.valley, self.park, self.premium])
        self.assertEqual(response.context["facilities"][1].from_price, Decimal("80.00"))

    def test_earliest_sort_uses_filtered_times(self):
        self.add_slot(self.premium, time(18), "20.00", 9)
        response = self.search(tee_time="evening", sort="earliest")
        self.assertEqual(list(response.context["facilities"]), [self.valley, self.premium])

    def test_all_filters_together(self):
        Booking.objects.create(slot=self.morning, user=self.user, num_players=1)
        response = self.search(
            course_name="park", location="Los Angeles", date=self.tomorrow.isoformat(),
            tee_time="morning", min_price="50", max_price="100", golfers="3",
            holes="18", rating="4", available="1", sort="price",
        )
        self.assert_courses(response, self.park)
        course = response.context["facilities"][0]
        self.assertEqual(course.from_price, Decimal("80.00"))
        self.assertEqual(course.slot_count, 1)

    def test_filters_cannot_match_unrelated_slots_on_same_course(self):
        self.assert_courses(self.search(course_name="Griffith", tee_time="morning", max_price="50"))
        self.assert_courses(self.search(course_name="Griffith", holes="18", max_price="50"))
        Booking.objects.create(slot=self.morning, user=self.user, num_players=3)
        self.assert_courses(self.search(course_name="Griffith", holes="18", golfers="2"))

    def test_multiple_slots_and_bookings_do_not_duplicate_courses(self):
        Booking.objects.create(slot=self.morning, user=self.user, num_players=1)
        Booking.objects.create(slot=self.morning, user=self.user, num_players=1)
        response = self.search(golfers="2")
        self.assert_courses(response, self.park, self.valley, self.premium)
        self.assertEqual(response.context["facilities"][0].slot_count, 2)

    def test_sort_control_submits_the_filter_form(self):
        response = self.search(course_name="Park", location="Angeles", golfers="3", sort="rating")
        self.assertContains(response, 'id="course-filters"')
        self.assertContains(response, 'name="sort" form="course-filters"')
        self.assertContains(response, 'value="rating" selected')
        self.assertContains(response, 'value="Park"')
        self.assertContains(response, 'value="Angeles"')
        self.assertContains(response, 'value="3"')

    def test_clear_all_link_has_no_query_parameters(self):
        response = self.search(q="Park", date=self.tomorrow.isoformat(), golfers="3 Players", sort="price")
        self.assertContains(response, '<a href="/courses/">Clear All</a>')
        self.assert_courses(self.client.get(reverse("courses")), self.park, self.valley, self.premium, self.empty)

    def test_invalid_get_parameters_show_errors_without_crashing(self):
        invalid = {
            "date": ["not-a-date", "2030-02-30", "99999-01-01"],
            "tee_time": ["night", "25:00"], "min_price": ["-1", "NaN", "Infinity", "1e9999", "abc"],
            "max_price": ["-1", "NaN", "201", "100.001"],
            "golfers": ["0", "5", "-3", "three", "3 Players extra"],
            "holes": ["0", "27", "abc"], "rating": ["NaN", "5", "-1"],
            "available": ["garbage"], "sort": ["distance", "-rating"],
            "q": ["x" * 201], "course_name": ["x" * 201], "location": ["x" * 201],
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.search(**{field: value})
                    self.assertIn(field, response.context["filter_form"].errors)
                    self.assert_courses(response)
                    self.assertContains(response, "Please correct the filters below.")

    def test_reversed_price_range_shows_error(self):
        response = self.search(min_price="100", max_price="50")
        self.assertContains(response, "Minimum price must not exceed maximum price.")
        self.assert_courses(response)

    def test_empty_results(self):
        response = self.search(course_name="No such course")
        self.assertContains(response, "No courses match your filters.")
        self.assertContains(response, "Try changing your search or clearing some filters.")
        self.assertContains(response, "0 matching courses")

    def test_homepage_quick_search_accepts_name_city_and_zip(self):
        for query, expected in (("Griffith", (self.park,)), ("angeles", (self.park, self.premium)),
                                ("90027", (self.park, self.premium)), ("91306", (self.valley,))):
            with self.subTest(query=query):
                response = self.search(q=query, date=self.tomorrow.isoformat(), golfers="3 Players")
                self.assert_courses(response, *expected)
                self.assertContains(response, 'name="q"')
                self.assertContains(response, f'value="{query}"')
                self.assertEqual(response.context["filter_form"].cleaned_data["golfers"], "3")

    def test_all_homepage_player_labels(self):
        for players, label in ((1, "1 Player"), (2, "2 Players"), (3, "3 Players"), (4, "4 Players")):
            with self.subTest(label=label):
                response = self.search(golfers=label)
                self.assert_courses(response, self.park, self.valley, self.premium)
                self.assertEqual(response.context["filter_form"].cleaned_data["golfers"], str(players))

    def test_clearing_quick_search_removes_its_restriction(self):
        self.assert_courses(self.search(q="Park"), self.park)
        self.assert_courses(self.search(q="", location="Los Angeles"), self.park, self.premium)

    def test_homepage_and_autocomplete_still_work(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'action="/courses/" method="get"')
        self.assertContains(response, "3 Players")
        self.assertContains(response, "data-autocomplete")
        response = self.client.get(reverse("facility_search"), {"q": "Griffith"})
        self.assertEqual(response.json()["results"][0]["id"], self.park.pk)

    def test_course_link_and_booking_flow_still_work(self):
        response = self.search(course_name="Griffith", golfers="3", holes="18")
        detail_url = reverse("facility_detail", args=[self.park.pk])
        self.assertContains(response, f'href="{detail_url}"')
        self.client.force_login(self.user)
        response = self.client.get(detail_url, {"date": self.tomorrow.isoformat()})
        self.assertContains(response, 'action="/checkout/"')
        response = self.client.get(reverse("checkout"), {"slot_id": self.morning.pk, "golfers": 3})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("book_slot"), {
            "slot_id": self.morning.pk, "golfers": 3, **VALID_PAYMENT,
        })
        self.assertRedirects(response, reverse("my_bookings"))
        self.assertEqual(Booking.objects.get().num_players, 3)
        self.assert_courses(self.search(course_name="Griffith", holes="18", golfers="2"))

    def test_query_count_does_not_grow_with_results(self):
        with self.assertNumQueries(1):
            response = self.search(available="1", golfers="2", sort="earliest")
            self.assert_courses(response, self.park, self.valley, self.premium)
