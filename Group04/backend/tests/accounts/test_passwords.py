from datetime import timedelta
from unittest.mock import patch
import json
from django.test import TestCase, override_settings
from django.utils import timezone
from accounts.models import PasswordResetToken, User


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
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
