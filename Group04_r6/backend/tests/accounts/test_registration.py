from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth.hashers import identify_hasher
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.models import EmailVerification, User


class RegistrationTests(TestCase):
    def test_verification_rechecks_database_when_request_has_a_stale_token(self):
        for purpose, endpoint in (
            (EmailVerification.Purpose.REGISTRATION, 'verify-email'),
            (EmailVerification.Purpose.EMAIL_CHANGE, 'verify-email-change'),
        ):
            for invalidation in ('used', 'replaced', 'expired'):
                with self.subTest(purpose=purpose, invalidation=invalidation):
                    user = User.objects.create_user(email=f'{purpose}-{invalidation}@example.com')
                    record, token = EmailVerification.issue(user, purpose, new_email='changed@example.com')
                    stale = EmailVerification.objects.select_related('user').get(pk=record.pk)
                    # Another request changes the token after this request has read it.
                    field = {'used': 'used_at', 'replaced': 'invalidated_at', 'expired': 'expires_at'}[invalidation]
                    EmailVerification.objects.filter(pk=record.pk).update(**{field: timezone.now()})
                    with patch('accounts.views.EmailVerification.resolve', return_value=stale):
                        response = self.client.get(f'/api/accounts/{endpoint}/{token}/')
                    self.assertEqual(response.status_code, 400)
                    self.assertIn('new verification link', response.data['detail'])
                    user.refresh_from_db()
                    self.assertFalse(user.email_verified)
                    self.assertNotEqual(user.email, 'changed@example.com')

    def test_registration_normalizes_email_hashes_password_and_requires_verification(self):
        password = 'RegisterPassword123!'
        response = self.client.post('/api/accounts/register/', {
            'email': '  Student@Example.COM  ', 'password': password,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='student@example.com')
        self.assertFalse(user.email_verified)
        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))
        self.assertEqual(identify_hasher(user.password).algorithm, 'argon2')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertNotIn(password, mail.outbox[0].body)

        duplicate = self.client.post('/api/accounts/register/', {
            'email': ' STUDENT@example.com ', 'password': password,
        }, content_type='application/json')
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

        link = next(word for word in mail.outbox[0].body.split() if word.startswith('http'))
        path = urlsplit(link).path
        self.assertEqual(self.client.get(path).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        reused = self.client.get(path)
        self.assertEqual(reused.status_code, 400)
        self.assertIn('new verification link', reused.data['detail'])

    def test_resend_replaces_registration_link_and_links_expire_at_24_hours(self):
        user = User.objects.create_user(email='unverified@example.com')
        old, old_token = EmailVerification.issue(user, EmailVerification.Purpose.REGISTRATION)
        response = self.client.post('/api/accounts/resend-verification/', {
            'email': ' UNVERIFIED@EXAMPLE.COM ',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        old.refresh_from_db()
        self.assertIsNotNone(old.invalidated_at)
        self.assertEqual(self.client.get(f'/api/accounts/verify-email/{old_token}/').status_code, 400)
        link = next(word for word in mail.outbox[0].body.split() if word.startswith('http'))
        latest = user.email_verifications.latest('id')
        self.assertAlmostEqual((latest.expires_at - latest.created_at).total_seconds(), timedelta(hours=24).total_seconds(), delta=1)
        with patch('django.utils.timezone.now', return_value=latest.expires_at):
            expired = self.client.get(urlsplit(link).path)
        self.assertEqual(expired.status_code, 400)
        self.assertIn('new verification link', expired.data['detail'])
        user.refresh_from_db()
        self.assertFalse(user.email_verified)
