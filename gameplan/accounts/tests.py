from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Profile, User, VerificationCode


class EditProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="golfer", email="golfer@example.com",
            password="Test-golf-password-27", email_verified=True,
        )
        cls.other_user = User.objects.create_user(username="other", email="other@example.com")
        Profile.objects.create(user=cls.other_user, bio="Another golfer")

    def setUp(self):
        self.client.force_login(self.user)
        self.profile = Profile.objects.create(
            user=self.user, bio="Weekend golfer", city="Northridge",
            zip_code="91330", skill_level="Intermediate", handicap=Decimal("12.5"),
        )
        self.data = {
            'bio': self.profile.bio, 'city': self.profile.city,
            'zip_code': self.profile.zip_code, 'skill_level': self.profile.skill_level,
            'handicap': str(self.profile.handicap),
        }
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=media.name))

    def image_upload(self, name="photo.png", image_format="PNG"):
        image = BytesIO()
        Image.new("RGB", (20, 20), "green").save(image, format=image_format)
        return SimpleUploadedFile(name, image.getvalue(), content_type=Image.MIME[image_format])

    def test_edit_page_loads_existing_information(self):
        self.assertEqual(reverse('edit_profile'), '/profile/edit/')
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'href="/profile/edit/"')
        response = self.client.get(reverse('edit_profile'))
        self.assertTemplateUsed(response, 'accounts/edit_profile.html')
        self.assertTemplateUsed(response, 'accounts/base.html')
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'list="golf-skill-levels"')
        self.assertContains(response, '<option value="Intermediate">')
        for field, value in self.data.items():
            self.assertEqual(str(response.context['form'][field].value()), value)

    def test_save_persists_after_refresh_and_login(self):
        self.data.update(bio="Learning to golf", city="Los Angeles", zip_code="90001-1234",
                         skill_level="Beginner", handicap="0.0")
        response = self.client.post(reverse('edit_profile'), self.data, follow=True)
        self.assertRedirects(response, reverse('profile'))
        self.assertContains(response, "Profile updated.")
        self.profile.refresh_from_db()
        for field, value in self.data.items():
            self.assertEqual(str(getattr(self.profile, field)), value)
        self.client.logout()
        response = self.client.post(reverse('login'), {
            'username': self.user.email, 'password': 'Test-golf-password-27',
        })
        self.assertRedirects(response, reverse('home'))
        for _ in range(2):
            response = self.client.get(reverse('profile'))
            for value in self.data.values():
                self.assertContains(response, value)

    def test_upload_replace_and_keep_images_when_editing_bio(self):
        response = self.client.post(reverse('edit_profile'), {
            **self.data, 'avatar': self.image_upload(),
            'cover_image': self.image_upload('cover.png'),
        })
        self.assertRedirects(response, reverse('profile'))
        self.profile.refresh_from_db()
        for field in (self.profile.avatar, self.profile.cover_image):
            self.assertTrue(field.storage.exists(field.name))
            self.assertContains(self.client.get(reverse('profile')), field.url)
            self.assertContains(self.client.get(reverse('edit_profile')), field.url)
        old_avatar = self.profile.avatar.name
        cover = self.profile.cover_image.name
        response = self.client.post(reverse('edit_profile'), {
            **self.data, 'avatar': self.image_upload('new-avatar.png'),
        })
        self.assertRedirects(response, reverse('profile'))
        self.profile.refresh_from_db()
        self.assertNotEqual(self.profile.avatar.name, old_avatar)
        avatar = self.profile.avatar.name
        self.data['bio'] = 'An updated bio'
        self.client.post(reverse('edit_profile'), self.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, self.data['bio'])
        self.assertEqual(self.profile.city, self.data['city'])
        self.assertEqual(self.profile.skill_level, self.data['skill_level'])
        self.assertEqual(self.profile.avatar.name, avatar)
        self.assertEqual(self.profile.cover_image.name, cover)

    def test_optional_fields_and_image_removal(self):
        self.profile.avatar.save('avatar.png', self.image_upload())
        self.profile.cover_image.save('cover.png', self.image_upload())
        response = self.client.post(reverse('edit_profile'), {
            'avatar-clear': 'on', 'cover_image-clear': 'on',
            'bio': '', 'city': '', 'zip_code': '', 'skill_level': '', 'handicap': '',
        }, follow=True)
        self.assertRedirects(response, reverse('profile'))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)
        self.assertFalse(self.profile.cover_image)
        self.assertIsNone(self.profile.handicap)
        self.assertContains(response, '<div class="profile-avatar-xl">G</div>', html=True)
        self.assertContains(response, 'Not shared')

    def test_cancel_returns_without_saving(self):
        response = self.client.get(reverse('edit_profile'))
        self.assertContains(response, '<a class="btn btn-outline" href="/profile/">Cancel</a>', html=True)
        self.client.get(reverse('profile'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, 'Weekend golfer')

    def test_user_without_profile_can_edit(self):
        self.profile.delete()
        response = self.client.get(reverse('edit_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())
        Profile.objects.filter(user=self.user).delete()
        response = self.client.post(reverse('edit_profile'), self.data)
        self.assertRedirects(response, reverse('profile'))
        self.assertEqual(Profile.objects.get(user=self.user).bio, self.data['bio'])

    def test_login_and_csrf_are_required(self):
        self.client.logout()
        for method in (self.client.get, self.client.post):
            response = method(reverse('edit_profile'))
            self.assertRedirects(response, '/login/?next=/profile/edit/')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(reverse('edit_profile'), self.data)
        self.assertEqual(response.status_code, 403)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, 'Weekend golfer')

    def test_submitted_user_cannot_change_another_profile(self):
        response = self.client.post(reverse('edit_profile'), {
            **self.data, 'bio': 'My updated bio', 'user': self.other_user.pk,
            'user_id': self.other_user.pk,
        })
        self.assertRedirects(response, reverse('profile'))
        self.assertEqual(Profile.objects.get(user=self.other_user).bio, 'Another golfer')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, 'My updated bio')

    def test_invalid_fields_show_errors_without_saving(self):
        invalid_values = [('zip_code', 'abcde'), ('zip_code', '1234'),
                          ('handicap', 'abc'), ('handicap', '54.1'), ('handicap', '-10.1'),
                          ('handicap', '12.34'), ('bio', 'x' * 501),
                          ('city', 'x' * 101), ('skill_level', 'x' * 21)]
        for field, value in invalid_values:
            with self.subTest(field=field, value=value):
                response = self.client.post(reverse('edit_profile'), {**self.data, field: value})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
                self.assertContains(response, 'errorlist')
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.bio, 'Weekend golfer')
                self.assertEqual(self.profile.zip_code, '91330')
                self.assertEqual(self.profile.handicap, Decimal('12.5'))

    def test_invalid_images_show_errors_without_saving(self):
        for field in ('avatar', 'cover_image'):
            corrupt = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')
            large = self.image_upload()
            large = SimpleUploadedFile('large.png', large.read() + b'\0' * (5 * 1024 * 1024),
                                       content_type='image/png')
            for upload in (corrupt, large, self.image_upload('photo.bmp', 'BMP')):
                with self.subTest(field=field, file=upload.name):
                    response = self.client.post(reverse('edit_profile'), {
                        **self.data, 'bio': 'Do not save this', field: upload,
                    })
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(field, response.context['form'].errors)
                    self.profile.refresh_from_db()
                    self.assertEqual(self.profile.bio, 'Weekend golfer')
                    self.assertFalse(getattr(self.profile, field))

    def test_profile_text_is_escaped(self):
        response = self.client.post(reverse('edit_profile'), {
            **self.data, 'bio': '<script>alert(1)</script>',
        }, follow=True)
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_account_pages_and_settings_still_work(self):
        for name in ('home', 'settings', 'my_gameplan', 'my_bookings', 'courses'):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        response = self.client.post(reverse('settings'), {'action': 'username', 'username': 'newgolfer'})
        self.assertRedirects(response, reverse('settings'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newgolfer')
        self.assertEqual(self.user.email, 'golfer@example.com')
        self.assertTrue(self.user.email_verified)
        self.assertTrue(self.user.check_password('Test-golf-password-27'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, 'Weekend golfer')

    def test_email_verification_still_works(self):
        self.client.logout()
        self.user.is_active = False
        self.user.email_verified = False
        self.user.save()
        verification = VerificationCode.objects.create(
            user=self.user, channel=VerificationCode.Channel.EMAIL,
            purpose=VerificationCode.Purpose.SIGNUP, code='123456',
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        session = self.client.session
        session['pending_user_id'] = self.user.pk
        session.save()
        response = self.client.post(reverse('verifyEmail'), {'code': '123456'})
        self.assertRedirects(response, reverse('login'))
        self.user.refresh_from_db()
        verification.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.email_verified)
        self.assertTrue(verification.used)

    def test_booking_and_cancellation_still_work(self):
        from facility.models import Booking, Facility, TimeSlot

        facility = Facility.objects.create(
            facility_name='Test course', street_address='123 Test St', city='Northridge',
            zip_code='91330', sport_type='Golf',
        )
        slot = TimeSlot.objects.create(
            facility=facility, date=timezone.localdate() + timedelta(days=1),
            start_time='09:00', price_per_player=Decimal('25.00'), max_players=4,
        )
        response = self.client.post(reverse('book_slot'), {'slot_id': slot.pk, 'golfers': 2})
        self.assertRedirects(response, reverse('my_bookings'))
        booking = Booking.objects.get(user=self.user, slot=slot)
        self.assertEqual(booking.num_players, 2)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        response = self.client.post(reverse('cancel_booking', args=[booking.pk]))
        self.assertRedirects(response, reverse('my_bookings'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
