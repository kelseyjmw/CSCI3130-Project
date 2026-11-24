from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace
import json
from urllib.parse import urlsplit
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from accounts.models import PasswordResetToken, User
from accounts.serializers import ChangePasswordSerializer, NewPasswordSerializer, RegisterSerializer


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PASSWORD_RESET_URL='http://127.0.0.1:5173/reset-password',
)
class PasswordManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='person@example.com',
            password='OldPassword123!',
            email_verified=True,
        )

    def post_json(self, path, data):
        return self.client.post(
            path,
            data=json.dumps(data),
            content_type='application/json',
        )

    def test_required_password_rules_are_consistent_for_registration_change_and_reset(self):
        cases = (
            (RegisterSerializer, {'email': 'password-rules@example.com'}, 'password'),
            (ChangePasswordSerializer, {'current_password': 'OldPassword123!'}, 'new_password'),
            (NewPasswordSerializer, {}, 'password'),
        )
        for serializer_class, fields, password_field in cases:
            for password, expected in (
                ('Foo12@', True), ('Ab1!', False), ('LettersOnly', False),
                ('Letters123', False), ('SpecialOnly!', False),
                ('Foo12_', True), ('Foo12-', True), ('Foo12 ', False),
                ('Foo١٢@', False), ('Aa1!😀', False),
            ):
                with self.subTest(flow=serializer_class.__name__, password=password):
                    serializer = serializer_class(data={**fields, password_field: password}, context={
                        'user': self.user, 'request': SimpleNamespace(user=self.user),
                    })
                    self.assertEqual(serializer.is_valid(), expected, serializer.errors)

    def test_password_endpoints_accept_required_minimum_and_preserve_spaces(self):
        response = self.post_json('/api/accounts/register/', {
            'email': 'minimum@example.com', 'password': 'Foo12@',
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.get(email='minimum@example.com').check_password('Foo12@'))

        self.login()
        response = self.post_json('/api/accounts/password/change/', {
            'current_password': 'OldPassword123!', 'new_password': ' Foo1@ ',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(' Foo1@ '))
        self.assertFalse(self.user.check_password('Foo1@'))

        _, token = PasswordResetToken.issue(self.user)
        response = self.post_json(f'/api/accounts/password-reset/{token}/', {'password': ' Reset1- '})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(' Reset1- '))
        self.assertFalse(self.user.check_password('Reset1-'))

    def test_reset_normalizes_email_has_generic_response_and_never_emails_passwords(self):
        known = self.post_json('/api/accounts/password-reset/request/', {'email': ' PERSON@EXAMPLE.COM '})
        unknown = self.post_json('/api/accounts/password-reset/request/', {'email': 'missing@example.com'})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.data, known.data)
        self.assertEqual(PasswordResetToken.objects.get().user, self.user)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        link = next(word for word in mail.outbox[0].body.split() if word.startswith('http'))
        self.assertTrue(link.startswith('http://127.0.0.1:5173/reset-password/'))
        token_from_link = urlsplit(link).path.rsplit('/', 1)[-1]
        self.assertEqual(PasswordResetToken.resolve(token_from_link).user, self.user)
        _, token = PasswordResetToken.issue(self.user)
        new_password = 'NewPassword123!'
        response = self.post_json(f'/api/accounts/password-reset/{token}/', {'password': new_password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        for message in mail.outbox:
            self.assertNotIn('OldPassword123!', message.body)
            self.assertNotIn(new_password, message.body)

    def login(self, client=None):
        client = client or self.client
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

    def test_reset_request_sends_email_for_existing_account(self):
        with patch('accounts.views.send_password_reset_link') as send:
            response = self.post_json(
                '/api/accounts/password-reset/request/',
                {'email': self.user.email},
            )

        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        self.assertEqual(PasswordResetToken.objects.count(), 1)

    def test_reset_token_expires_after_30_minutes_and_is_one_time(self):
        token, raw_token = PasswordResetToken.issue(self.user)
        token.created_at = timezone.now() - timedelta(minutes=30, seconds=1)
        token.save(update_fields=['created_at'])
        self.assertFalse(PasswordResetToken.resolve(raw_token).is_valid)

        token, raw_token = PasswordResetToken.issue(self.user)
        with patch('accounts.views.send_password_change_notice'):
            response = self.post_json(
                f'/api/accounts/password-reset/{raw_token}/',
                {'password': 'NewPassword123!'},
            )
            second_response = self.post_json(
                f'/api/accounts/password-reset/{raw_token}/',
                {'password': 'AnotherPassword123!'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(second_response.status_code, 400)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password('NewPassword123!'))

    def test_password_change_keeps_current_session_and_invalidates_other_sessions(self):
        other_client = self.client.__class__()
        self.login()
        self.login(other_client)

        with patch('accounts.views.send_password_change_notice') as send:
            response = self.post_json(
                '/api/accounts/password/change/',
                {
                    'current_password': 'OldPassword123!',
                    'new_password': 'NewPassword123!',
                },
            )

        self.assertEqual(response.status_code, 200)
        send.assert_called_once_with(self.user.email)
        self.assertEqual(self.client.get('/api/accounts/me/').status_code, 200)
        self.assertEqual(other_client.get('/api/accounts/me/').status_code, 403)

    def test_password_reset_invalidates_sessions_and_does_not_log_in(self):
        other_client = self.client.__class__()
        self.login()
        self.login(other_client)
        _, raw_token = PasswordResetToken.issue(self.user)

        with patch('accounts.views.send_password_change_notice') as send:
            response = self.post_json(
                f'/api/accounts/password-reset/{raw_token}/',
                {'password': 'NewPassword123!'},
            )

        self.assertEqual(response.status_code, 200)
        send.assert_called_once_with(self.user.email)
        self.assertEqual(self.client.get('/api/accounts/me/').status_code, 403)
        self.assertEqual(other_client.get('/api/accounts/me/').status_code, 403)
