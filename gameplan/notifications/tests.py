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

    def test_feed_combines_categories_and_read_states_newest_first(self):
        older = self.make_notification()
        newer = self.make_notification()
        newer.category = Notification.Category.BOOKING
        newer.is_read = True
        newer.save()
        private = self.make_notification(self.other)
        private.title = "Other user's private event"
        private.save()
        response = self.client.get(reverse("notifications:feed"))
        self.assertEqual(list(response.context["updates"]), [newer, older])
        self.assertNotIn(private.title, response.json()["html"])
        self.assertEqual(response.json()["unread_count"], 1)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertNotIn("GamePlan Updates", response.json()["html"])
        self.assertNotIn("Booking Updates", response.json()["html"])

    def test_empty_feed(self):
        response = self.client.get(reverse("notifications:feed"))
        self.assertEqual(response.json()["html"].strip(), "")
        self.assertContains(self.client.get(reverse("my_gameplan")), "No notifications yet", count=1)
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertIsNone(response.json()["next_cursor"])

    def test_legacy_url_redirects_to_shared_dropdown(self):
        self.assertRedirects(self.client.get(reverse("notifications:list")),
                             f"{reverse('my_gameplan')}?notifications=open")

    def test_mark_one_read_and_refresh_bell_on_other_pages(self):
        first = self.make_notification()
        second = self.make_notification()
        other = self.make_notification(self.other)
        response = self.client.post(reverse("notifications:mark_read", args=[first.pk]),
                                    HTTP_ACCEPT="application/json")
        self.assertEqual(response.json(), {"unread_count": 1, "destination": reverse("settings")})
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_read)
        self.assertFalse(second.is_read)
        other.refresh_from_db()
        self.assertFalse(other.is_read)
        feed = self.client.get(reverse("notifications:feed"))
        self.assertEqual(list(feed.context["updates"]), [second, first])
        self.assertEqual(feed.json()["html"].count('class="notification-item is-unread"'), 1)
        for name in ("home", "my_gameplan", "my_bookings", "settings", "profile", "courses", "lessons"):
            with self.subTest(page=name):
                page = self.client.get(reverse(name))
                self.assertContains(page, "Notifications, 1 unread")
                self.assertContains(page, 'id="notification-dropdown"', count=1)
                self.assertContains(page, 'data-notifications-toggle aria-controls="notification-dropdown"',
                                    count=3 if name == "my_gameplan" else 2)
                self.assertContains(page, 'aria-label="Search courses or locations"')
                self.assertContains(page, 'data-account-menu')
        self.client.post(reverse("notifications:mark_read", args=[first.pk]))
        self.assertEqual(Notification.objects.filter(recipient=self.user, is_read=False).count(), 1)

    def test_cannot_mark_another_users_notification(self):
        notification = self.make_notification(self.other)
        response = self.client.post(reverse("notifications:mark_read", args=[notification.pk]))
        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_all_only_changes_own_notifications(self):
        for _ in range(25):
            self.make_notification()
        other = self.make_notification(self.other)
        response = self.client.post(reverse("notifications:mark_all_read"), HTTP_ACCEPT="application/json")
        self.assertFalse(Notification.objects.filter(recipient=self.user, is_read=False).exists())
        other.refresh_from_db()
        self.assertFalse(other.is_read)
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 25)
        feed = self.client.get(reverse("notifications:feed"))
        self.assertEqual(len(feed.context["updates"]), 20)
        self.assertNotIn("is-unread", feed.json()["html"])
        older = self.client.get(reverse("notifications:feed"), {"before": feed.json()["next_cursor"]})
        self.assertEqual(len(older.context["updates"]), 5)
        self.assertNotIn("is-unread", older.json()["html"])

    def test_get_requests_do_not_mark_read(self):
        notification = self.make_notification()
        self.client.get(reverse("notifications:list"))
        self.client.get(reverse("notifications:feed"))
        response = self.client.get(reverse("notifications:feed"), {"count_only": "1"})
        self.assertEqual(response.json(), {"unread_count": 1})
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
        client.get(reverse("my_gameplan"))
        response = client.post(reverse("notifications:mark_read", args=[notification.pk]), {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertEqual(client.post(reverse("notifications:mark_all_read"), {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }, HTTP_ACCEPT="application/json").status_code, 200)

    def test_all_routes_require_login(self):
        notification = self.make_notification()
        self.client.logout()
        routes = [
            (self.client.get, reverse("notifications:list")),
            (self.client.get, reverse("notifications:feed")),
            (self.client.post, reverse("notifications:mark_read", args=[notification.pk])),
            (self.client.post, reverse("notifications:mark_all_read")),
        ]
        for method, url in routes:
            self.assertRedirects(method(url), f"{reverse('login')}?next={url}")

    def test_notification_text_is_escaped(self):
        notification = self.make_notification()
        notification.message = '<script>alert("test")</script>'
        notification.save()
        response = self.client.get(reverse("notifications:feed"))
        self.assertIn("&lt;script&gt;", response.json()["html"])
        self.assertNotIn(notification.message, response.json()["html"])

    def test_deleted_booking_keeps_notification_history(self):
        booking = Booking.objects.create(user=self.user, slot=create_slot())
        notification = notify_booking_confirmed(booking)
        booking.delete()
        notification.refresh_from_db()
        self.assertIsNone(notification.booking)
        self.assertIn(notification.message, self.client.get(reverse("notifications:feed")).json()["html"])
        response = self.client.post(reverse("notifications:mark_read", args=[notification.pk]),
                                    HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["destination"], reverse("my_bookings"))

    def test_older_notifications_remain_accessible_when_new_events_arrive(self):
        notifications = [self.make_notification() for _ in range(45)]
        # Equal timestamps also preserve the model's descending primary-key order.
        Notification.objects.update(created_at=timezone.now())
        first = self.client.get(reverse("notifications:feed"))
        seen = list(first.context["updates"])
        self.make_notification()
        cursor = first.json()["next_cursor"]
        while cursor:
            response = self.client.get(reverse("notifications:feed"), {"before": cursor})
            seen.extend(response.context["updates"])
            cursor = response.json()["next_cursor"]
        self.assertEqual([item.pk for item in seen], [item.pk for item in reversed(notifications)])
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 46)

    def test_cursor_cannot_access_another_users_notification(self):
        other = self.make_notification(self.other)
        self.assertEqual(self.client.get(reverse("notifications:feed"), {"before": other.pk}).status_code, 404)
        self.assertEqual(self.client.get(reverse("notifications:feed"), {"before": "bad"}).status_code, 400)

    def test_destination_rechecks_booking_ownership(self):
        booking = Booking.objects.create(user=self.other, slot=create_slot())
        notification = self.make_notification()
        Notification.objects.filter(pk=notification.pk).update(
            booking=booking, category=Notification.Category.BOOKING,
        )
        response = self.client.post(reverse("notifications:mark_read", args=[notification.pk]),
                                    HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["destination"], reverse("my_bookings"))


class BookingNotificationTests(TestCase):
    def setUp(self):
        for target in ("facility.views.send_booking_confirmation", "facility.views.send_booking_cancellation"):
            delivery = patch(target)
            delivery.start()
            self.addCleanup(delivery.stop)
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
        response = self.client.get(reverse("notifications:feed"))
        self.assertEqual(list(response.context["updates"]), [notification])
        url = reverse("booking_confirmation", args=[booking.pk])
        response = self.client.post(reverse("notifications:mark_read", args=[notification.pk]),
                                    HTTP_ACCEPT="application/json")
        self.assertEqual(response.json(), {"destination": url, "unread_count": 0})
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
        response = self.client.get(reverse("notifications:feed"))
        self.assertEqual(response.context["updates"][0], cancelled)
        self.assertIn("is-cancelled", response.json()["html"])
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
        self.assertEqual(self.client.get(reverse("notifications:feed")).context["updates"], [])
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
        delivery = patch("accounts.verification.send_mail")
        delivery.start()
        self.addCleanup(delivery.stop)
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
        response = self.client.get(reverse("notifications:feed"))
        self.assertEqual(list(response.context["updates"]), [notification])
        response = self.client.post(reverse("notifications:mark_read", args=[notification.pk]),
                                    HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["destination"], reverse("settings"))
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
