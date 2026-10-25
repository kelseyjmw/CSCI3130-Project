from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
import json
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import TestCase
from accounts.models import User


class SessionExpirationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='session-user@example.com',
            password='OldPassword123!',
            email_verified=True,
        )
        self.start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)

    def login(self, client=None):
        client = client or self.client
        with patch('django.utils.timezone.now', return_value=self.start):
            response = client.post(
                '/api/accounts/login/',
                data=json.dumps({
                    'email': self.user.email,
                    'password': 'OldPassword123!',
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        return client
    def test_unverified_user_cannot_login(self):
        unverified_user = User.objects.create_user(
            email='unverified-user@example.com',
            password='OldPassword123!',
            email_verified=False,
        )
        response = self.client.post(
            '/api/accounts/login/',
            data=json.dumps({
                'email': unverified_user.email,
                'password': 'OldPassword123!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json().get('error'),
            'Please verify your email address before logging in.',
        )
        self.assertNotIn(settings.SESSION_COOKIE_NAME, self.client.cookies)

    def session(self, client):
        session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
        return Session.objects.get(session_key=session_key)

    def assert_expiration_near(self, session, expected):
        self.assertAlmostEqual(
            session.expire_date.timestamp(),
            expected.timestamp(),
            delta=1,
        )

    def test_new_authenticated_session_expires_after_30_days(self):
        self.login()

        session = self.session(self.client)

        self.assert_expiration_near(
            session,
            self.start + timedelta(days=30),
        )

    def test_authenticated_request_renews_session_expiration(self):
        self.login()
        renewed_at = self.start + timedelta(days=1)

        with patch('django.utils.timezone.now', return_value=renewed_at):
            response = self.client.get('/api/accounts/me/')

        self.assertEqual(response.status_code, 200)
        self.assert_expiration_near(
            self.session(self.client),
            renewed_at + timedelta(days=30),
        )

    def test_session_is_rejected_at_and_after_stored_expiration(self):
        self.login()
        expires_at = self.start + timedelta(days=30)
        session = self.session(self.client)
        session.expire_date = expires_at
        session.save(update_fields=['expire_date'])

        with patch('django.utils.timezone.now', return_value=expires_at):
            at_deadline = self.client.get('/api/accounts/me/')

        with patch(
            'django.utils.timezone.now',
            return_value=expires_at + timedelta(seconds=1),
        ):
            after_deadline = self.client.get('/api/accounts/me/')

        self.assertEqual(at_deadline.status_code, 403)
        self.assertEqual(after_deadline.status_code, 403)

    def test_expired_session_cannot_become_authenticated_from_a_request(self):
        self.login()
        expires_at = self.start + timedelta(days=30)
        session_key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        Session.objects.filter(session_key=session_key).update(
            expire_date=expires_at,
        )

        with patch('django.utils.timezone.now', return_value=expires_at):
            response = self.client.get('/api/accounts/me/')

        self.assertEqual(response.status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_activity_in_one_session_does_not_renew_another_session(self):
        first_client = self.login()
        second_client = self.login(self.client.__class__())
        second_expiration = self.session(second_client).expire_date
        renewed_at = self.start + timedelta(days=1)

        with patch('django.utils.timezone.now', return_value=renewed_at):
            response = first_client.get('/api/accounts/me/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.session(second_client).expire_date, second_expiration)

        with patch('django.utils.timezone.now', return_value=second_expiration):
            response = second_client.get('/api/accounts/me/')

        self.assertEqual(response.status_code, 403)

    def test_logout_invalidates_only_the_current_session(self):
        first_client = self.login()
        second_client = self.login(self.client.__class__())

        logout_time = self.start + timedelta(days=1)
        with patch('django.utils.timezone.now', return_value=logout_time):
            response = first_client.post('/api/accounts/logout/')
            first_status = first_client.get('/api/accounts/me/').status_code
            second_status = second_client.get('/api/accounts/me/').status_code

        self.assertEqual(response.status_code, 200)
        self.assertEqual(first_status, 403)
        self.assertEqual(second_status, 200)
