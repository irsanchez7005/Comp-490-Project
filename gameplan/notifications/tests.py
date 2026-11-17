from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from accounts.models import VerificationCode
from facility.models import Booking
from facility.tests import VALID_PAYMENT, create_slot, create_user
from facility.views import _create_paid_booking
from .models import Notification
from .services import create_notification, notify_booking_confirmed, notify_email_verified


class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other = create_user("other")

    def setUp(self):
        self.client.force_login(self.user)

    def make_notification(self, user=None, **kwargs):
        return create_notification(
            user or self.user, Notification.Category.GAMEPLAN, "account_updated",
            "Account Updated", "Account information was updated.", **kwargs,
        )

    def test_new_notifications_are_unread_and_duplicates_keep_history(self):
        first = self.make_notification(event_key="account:example:1")
        self.assertFalse(first.is_read)
        first.is_read = True
        first.save()
        second = self.make_notification(event_key="account:example:1")
        self.assertEqual(second.pk, first.pk)
        self.assertTrue(second.is_read)
        self.assertEqual(Notification.objects.count(), 1)

    def test_event_keys_are_scoped_to_each_recipient(self):
        self.make_notification(event_key="example")
        self.make_notification(self.other, event_key="example")
        self.assertEqual(Notification.objects.count(), 2)

    def test_separate_events_without_keys_remain_separate(self):
        self.make_notification()
        self.make_notification()
        self.assertEqual(Notification.objects.count(), 2)

    def test_service_rejects_another_users_booking(self):
        booking = Booking.objects.create(user=self.other, slot=create_slot())
        with self.assertRaises(ValueError):
            self.make_notification(booking=booking)
        self.assertFalse(Notification.objects.exists())

    def test_service_rejects_unknown_categories(self):
        with self.assertRaises(ValueError):
            create_notification(self.user, "unknown", "test", "Test", "Test")

    def test_page_only_shows_own_notifications_newest_first(self):
        older = self.make_notification()
        newer = self.make_notification()
        private = self.make_notification(self.other)
        private.title = "Other user's private event"
        private.save()
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(list(response.context["gameplan_updates"]), [newer, older])
        self.assertNotContains(response, private.title)
        self.assertContains(response, "Notifications, 2 unread")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(response, "Your latest GamePlan activity in one place.")

    def test_empty_sections(self):
        response = self.client.get(reverse("notifications:list"))
        self.assertContains(response, "You're all caught up", count=2)
        self.assertContains(response, "disabled>Mark All as Read")

    def test_mark_one_read_and_refresh_bell_on_other_pages(self):
        first = self.make_notification()
        second = self.make_notification()
        response = self.client.post(reverse("notifications:mark_read", args=[first.pk]), follow=True)
        self.assertContains(response, "Notifications, 1 unread")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_read)
        self.assertFalse(second.is_read)
        self.assertContains(response, 'class="notification-item is-unread"', count=1)
        for name in ("home", "my_gameplan", "my_bookings", "settings", "profile", "courses"):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), "Notifications, 1 unread")
        self.client.post(reverse("notifications:mark_read", args=[first.pk]))
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)

    def test_cannot_mark_another_users_notification(self):
        notification = self.make_notification(self.other)
        response = self.client.post(reverse("notifications:mark_read", args=[notification.pk]))
        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_all_only_changes_own_notifications(self):
        self.make_notification()
        self.make_notification()
        other = self.make_notification(self.other)
        response = self.client.post(reverse("notifications:mark_all_read"), follow=True)
        self.assertFalse(Notification.objects.filter(recipient=self.user, is_read=False).exists())
        other.refresh_from_db()
        self.assertFalse(other.is_read)
        self.assertContains(response, "Notifications, 0 unread")
        self.assertNotContains(response, 'class="notification-badge"')

    def test_get_requests_do_not_mark_read(self):
        notification = self.make_notification()
        self.client.get(reverse("notifications:list"))
        for name, args in (("notifications:mark_read", [notification.pk]), ("notifications:mark_all_read", [])):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 405)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_post_actions_require_csrf(self):
        notification = self.make_notification()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for name, args in (("notifications:mark_read", [notification.pk]), ("notifications:mark_all_read", [])):
            url = reverse(name, args=args)
            self.assertEqual(client.post(url).status_code, 403)
        client.get(reverse("notifications:list"))
        response = client.post(reverse("notifications:mark_read", args=[notification.pk]), {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_all_routes_require_login(self):
        notification = self.make_notification()
        self.client.logout()
        routes = [
            (self.client.get, reverse("notifications:list")),
            (self.client.post, reverse("notifications:mark_read", args=[notification.pk])),
            (self.client.post, reverse("notifications:mark_all_read")),
        ]
        for method, url in routes:
            self.assertRedirects(method(url), f"{reverse('login')}?next={url}")

    def test_notification_text_is_escaped(self):
        notification = self.make_notification()
        notification.message = '<script>alert("test")</script>'
        notification.save()
        response = self.client.get(reverse("notifications:list"))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, notification.message)

    def test_deleted_booking_keeps_notification_history(self):
        booking = Booking.objects.create(user=self.user, slot=create_slot())
        notification = notify_booking_confirmed(booking)
        booking.delete()
        notification.refresh_from_db()
        self.assertIsNone(notification.booking)
        self.assertContains(self.client.get(reverse("notifications:list")), notification.message)


class BookingNotificationTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.slot = create_slot()
        self.client.force_login(self.user)

    def book(self, **overrides):
        return self.client.post(reverse("book_slot"), {
            **VALID_PAYMENT, "slot_id": self.slot.pk, "golfers": 2, **overrides,
        })

    def test_successful_booking_creates_real_confirmation_and_link(self):
        self.assertRedirects(self.book(), reverse("my_bookings"))
        booking = Booking.objects.get()
        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.category, Notification.Category.BOOKING)
        self.assertEqual(notification.title, "Booking Confirmed")
        for text in (self.slot.facility.facility_name, date_format(self.slot.date, "F j, Y"),
                     "9:30 AM", f"Booking #{booking.pk}"):
            self.assertIn(text, notification.message)
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(list(response.context["booking_updates"]), [notification])
        self.assertEqual(list(response.context["gameplan_updates"]), [])
        url = reverse("booking_confirmation", args=[booking.pk])
        self.assertContains(response, f'href="{url}"')
        self.assertEqual(self.client.get(url).status_code, 200)
        notify_booking_confirmed(booking)
        self.assertEqual(Notification.objects.count(), 1)

    def test_cancel_creates_one_notification_and_preserves_confirmation(self):
        self.book()
        booking = Booking.objects.get()
        url = reverse("cancel_booking", args=[booking.pk])
        self.assertRedirects(self.client.post(url), reverse("my_bookings"))
        self.client.post(url)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertEqual(Notification.objects.count(), 2)
        cancelled = Notification.objects.get(event_type="booking_cancelled")
        self.assertEqual(cancelled.title, "Booking Cancelled")
        self.assertIn("9:30 AM has been successfully cancelled", cancelled.message)
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.context["booking_updates"][0], cancelled)
        self.assertContains(response, "is-cancelled")
        self.assertContains(self.client.get(reverse("booking_confirmation", args=[booking.pk])), "Booking Cancelled")

    def test_already_cancelled_booking_does_not_create_event(self):
        booking = Booking.objects.create(user=self.user, slot=self.slot, status=Booking.Status.CANCELLED)
        self.client.post(reverse("cancel_booking", args=[booking.pk]))
        self.assertFalse(Notification.objects.exists())

    def test_invalid_booking_attempts_do_not_notify(self):
        for data in ({"cvv": "1"}, {"slot_id": "bad"}, {"golfers": 0}, {"golfers": 5}):
            with self.subTest(data=data):
                self.book(**data)
                self.assertFalse(Notification.objects.exists())
                self.assertFalse(Booking.objects.exists())
        self.slot.date = timezone.localdate() - timedelta(days=1)
        self.slot.save()
        self.book()
        self.assertFalse(Notification.objects.exists())

    def test_slot_full_at_final_check_does_not_notify(self):
        Booking.objects.create(user=self.user, slot=self.slot, num_players=4)
        self.assertIsNone(_create_paid_booking(self.slot, self.user, 1, "1111222233334444"))
        self.assertFalse(Notification.objects.exists())

    def test_other_user_cannot_open_or_cancel_booking(self):
        self.book()
        booking = Booking.objects.get()
        self.client.force_login(create_user("someone"))
        url = reverse("booking_confirmation", args=[booking.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("cancel_booking", args=[booking.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("notifications:list")), f'href="{url}"')
        self.assertEqual(Notification.objects.count(), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_get_cancellation_does_not_notify(self):
        self.book()
        self.assertEqual(self.client.get(reverse("cancel_booking", args=[Booking.objects.get().pk])).status_code, 405)
        self.assertEqual(Notification.objects.count(), 1)

    def test_rolled_back_booking_leaves_no_notification(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.book()
                raise ValueError("Rollback")
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_notification_failure_rolls_back_booking(self):
        with patch("facility.views.notify_booking_confirmed", side_effect=ValueError("Failed")):
            with self.assertRaises(ValueError):
                self.book()
        self.assertFalse(Booking.objects.exists())

    def test_notification_failure_rolls_back_cancellation(self):
        self.book()
        booking = Booking.objects.get()
        with patch("facility.views.notify_booking_cancelled", side_effect=ValueError("Failed")):
            with self.assertRaises(ValueError):
                self.client.post(reverse("cancel_booking", args=[booking.pk]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(Notification.objects.count(), 1)


class AccountNotificationTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)

    def verify_email(self, code="123456"):
        self.client.logout()
        self.user.is_active = False
        self.user.save()
        VerificationCode.objects.create(
            user=self.user, channel="email", purpose="signup", code="123456",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        session = self.client.session
        session["pending_user_id"] = self.user.pk
        session.save()
        return self.client.post(reverse("verifyEmail"), {"code": code})

    def assert_account_event(self, event_type):
        notification = Notification.objects.get()
        self.assertEqual(notification.event_type, event_type)
        self.assertEqual(notification.category, Notification.Category.GAMEPLAN)
        self.assertIsNone(notification.booking)
        self.assertEqual(notification.recipient, self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(list(response.context["gameplan_updates"]), [notification])
        self.assertEqual(list(response.context["booking_updates"]), [])
        return notification

    def test_successful_email_verification_notifies_once(self):
        self.assertRedirects(self.verify_email(), reverse("login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assert_account_event("email_verified")
        notify_email_verified(self.user)
        self.assertEqual(Notification.objects.count(), 1)

    def test_invalid_email_code_does_not_notify(self):
        self.verify_email("654321")
        self.assertFalse(Notification.objects.exists())

    def test_expired_email_code_does_not_notify(self):
        self.verify_email("654321")
        VerificationCode.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.client.post(reverse("verifyEmail"), {"code": "123456"})
        self.assertFalse(Notification.objects.exists())

    def test_locked_verification_does_not_notify(self):
        self.verify_email("654321")
        VerificationCode.objects.update(locked_until=timezone.now() + timedelta(minutes=1))
        self.client.post(reverse("verifyEmail"), {"code": "123456"})
        self.assertFalse(Notification.objects.exists())

    def test_username_change_notifies(self):
        self.client.post(reverse("settings"), {"action": "username", "username": "newgolfer"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "newgolfer")
        self.assert_account_event("account_updated")

    def test_email_change_notifies(self):
        self.client.post(reverse("settings"), {"action": "email", "email": "new@example.com"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assert_account_event("account_updated")

    def test_unchanged_or_invalid_account_fields_do_not_notify(self):
        other = create_user("other")
        cases = [
            ("username", self.user.username), ("email", self.user.email),
            ("email", self.user.email.upper()), ("username", f" {self.user.username} "),
            ("email", "bad"), ("username", ""),
            ("username", other.username), ("email", other.email),
        ]
        for action, value in cases:
            with self.subTest(action=action, value=value):
                self.client.post(reverse("settings"), {"action": action, action: value})
                self.assertFalse(Notification.objects.exists())

    def test_repeated_account_submission_does_not_duplicate(self):
        for _ in range(2):
            self.client.post(reverse("settings"), {"action": "username", "username": "changed"})
        self.assertEqual(Notification.objects.count(), 1)

    def test_settings_password_change_notifies_without_password_details(self):
        self.client.post(reverse("settings"), {"action": "verify_password", "password": "test-password"})
        self.assertFalse(Notification.objects.exists())
        response = self.client.post(reverse("settings"), {
            "action": "set_password", "new_password1": "Changed-Golf-Password-27",
            "new_password2": "Changed-Golf-Password-27",
        })
        self.assertRedirects(response, reverse("settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Changed-Golf-Password-27"))
        notification = self.assert_account_event("password_updated")
        self.assertNotIn("Changed-Golf-Password-27", notification.message)
        self.assertNotIn(self.user.password, notification.event_key)

    def test_invalid_or_unverified_password_change_does_not_notify(self):
        data = {"action": "set_password", "new_password1": "Changed-Golf-Password-27",
                "new_password2": "Changed-Golf-Password-27"}
        self.client.post(reverse("settings"), data)
        self.assertFalse(Notification.objects.exists())
        self.client.post(reverse("settings"), {"action": "verify_password", "password": "test-password"})
        self.client.post(reverse("settings"), {**data, "new_password2": "mismatch"})
        self.assertFalse(Notification.objects.exists())

    def test_password_reset_notifies_only_after_new_password_saved(self):
        self.client.logout()
        self.client.post(reverse("password_reset"), {"email": self.user.email})
        verification = VerificationCode.objects.get(purpose="password_reset")
        self.client.post(reverse("password_reset_done"), {"code": verification.code})
        self.assertFalse(Notification.objects.exists())
        data = {"new_password1": "Reset-Golf-Password-27", "new_password2": "Reset-Golf-Password-27"}
        self.client.post(reverse("password_reset_confirm"), {**data, "new_password2": "mismatch"})
        self.assertFalse(Notification.objects.exists())
        self.assertRedirects(self.client.post(reverse("password_reset_confirm"), data), reverse("password_reset_complete"))
        self.client.post(reverse("password_reset_confirm"), data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(data["new_password1"]))
        self.assert_account_event("password_updated")

    def test_unverified_password_reset_does_not_notify(self):
        self.client.logout()
        self.client.post(reverse("password_reset_confirm"), {
            "new_password1": "Reset-Golf-Password-27", "new_password2": "Reset-Golf-Password-27",
        })
        self.assertFalse(Notification.objects.exists())

    def test_notification_failure_rolls_back_account_change(self):
        with patch("accounts.views.notify_account_updated", side_effect=ValueError("Failed")):
            with self.assertRaises(ValueError):
                self.client.post(reverse("settings"), {"action": "username", "username": "changed"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "golfer")
