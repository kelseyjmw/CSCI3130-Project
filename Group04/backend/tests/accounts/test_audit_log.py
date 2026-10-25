from unittest.mock import patch
from django.core.exceptions import PermissionDenied
from accounts.models import AuditLog, EmailVerification, PasswordResetToken
from .helpers import ReviewTestBase

URL = '/api/accounts/admin/audit-log/'


class AuditLogTests(ReviewTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def make_entry(self, **overrides):
        values = dict(
            actor=self.admin.pk, target=self.other.pk,
            action='role_change', result='success', reason='Seller role granted.',
        )
        values.update(overrides)
        return AuditLog.objects.create(**values)

    def all_text(self):
        # Every stored field of every record, joined, for secret scanning.
        return ' '.join(
            str(value)
            for row in AuditLog.objects.values()
            for value in row.values()
        )

    # --- record contents ---

    def test_record_has_required_fields(self):
        self.make_entry()

        record = self.client.get(URL).data['results'][0]

        self.assertEqual(
            set(record),
            {'id', 'timestamp', 'actor', 'target', 'action', 'result', 'reason'},
        )
        self.assertEqual(record['actor'], self.admin.pk)
        self.assertEqual(record['target'], self.other.pk)
        self.assertEqual(record['action'], 'role_change')
        self.assertEqual(record['result'], 'success')
        self.assertEqual(record['reason'], 'Seller role granted.')

    def test_timestamp_is_utc(self):
        self.make_entry()

        timestamp = self.client.get(URL).data['results'][0]['timestamp']

        self.assertTrue(timestamp.endswith('Z') or timestamp.endswith('+00:00'))

    def test_actor_and_target_may_be_empty(self):
        self.make_entry(actor=None, target=None, action='login', result='failed', reason='')

        record = self.client.get(URL).data['results'][0]

        self.assertIsNone(record['actor'])
        self.assertIsNone(record['target'])
        self.assertEqual(record['reason'], '')

    # --- ordering and pagination ---

    def test_records_are_newest_first(self):
        first = self.make_entry(action='login')
        second = self.make_entry(action='logout')
        third = self.make_entry(action='role_change')

        ids = [row['id'] for row in self.client.get(URL).data['results']]

        self.assertEqual(ids, [third.pk, second.pk, first.pk])

    def test_results_are_paginated_newest_first_across_pages(self):
        entries = [self.make_entry(reason=f'entry {i}') for i in range(30)]

        first_page = self.client.get(URL).data
        second_page = self.client.get(URL, {'page': 2}).data

        self.assertEqual(first_page['count'], 30)
        self.assertEqual(len(first_page['results']), 25)
        self.assertEqual(len(second_page['results']), 5)
        self.assertEqual(first_page['results'][0]['id'], entries[-1].pk)
        self.assertEqual(second_page['results'][-1]['id'], entries[0].pk)

    def test_page_out_of_range_returns_404(self):
        self.assertEqual(self.client.get(URL, {'page': 99}).status_code, 404)

    # --- who can view ---

    def test_administrator_can_view(self):
        self.make_entry()
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_moderator_cannot_view(self):
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_regular_user_cannot_view(self):
        self.client.force_authenticate(self.applicant)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_anonymous_cannot_view(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(URL).status_code, (401, 403))

    # --- records cannot be changed or deleted ---

    def test_api_offers_no_way_to_change_or_delete(self):
        entry = self.make_entry()

        for method in ('post', 'put', 'patch', 'delete'):
            response = getattr(self.client, method)(URL, {}, format='json')
            self.assertEqual(response.status_code, 405, method)
            detail = getattr(self.client, method)(f'{URL}{entry.pk}/', {}, format='json')
            self.assertEqual(detail.status_code, 404, method)

        self.assertEqual(AuditLog.objects.count(), 1)

    def test_record_cannot_be_saved_again(self):
        entry = self.make_entry()
        entry.reason = 'Edited'

        with self.assertRaises(PermissionDenied):
            entry.save()

        entry.refresh_from_db()
        self.assertEqual(entry.reason, 'Seller role granted.')

    def test_record_cannot_be_deleted(self):
        entry = self.make_entry()

        with self.assertRaises(PermissionDenied):
            entry.delete()

        self.assertTrue(AuditLog.objects.filter(pk=entry.pk).exists())

    def test_bulk_update_and_delete_are_blocked(self):
        self.make_entry()

        with self.assertRaises(PermissionDenied):
            AuditLog.objects.all().update(reason='Edited')
        with self.assertRaises(PermissionDenied):
            AuditLog.objects.all().delete()

        self.assertEqual(AuditLog.objects.get().reason, 'Seller role granted.')

    # --- no secrets in records ---

    def test_failed_login_does_not_store_the_password(self):
        self.client.force_authenticate(None)

        self.client.post(
            '/api/accounts/login/',
            {'email': self.other.email, 'password': 'SuperSecretGuess99!'},
            format='json',
        )

        self.assertTrue(AuditLog.objects.filter(action='login', result='failed').exists())
        self.assertNotIn('SuperSecretGuess99!', self.all_text())

    def test_password_reset_does_not_store_the_token_or_password(self):
        _, raw_token = PasswordResetToken.issue(self.other)
        self.client.force_authenticate(None)

        with patch('accounts.views.send_password_change_notice'):
            response = self.client.post(
                f'/api/accounts/password-reset/{raw_token}/',
                {'password': 'BrandNewPass123!'},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='password_reset').exists())
        text = self.all_text()
        self.assertNotIn(raw_token, text)
        self.assertNotIn(PasswordResetToken.hash_token(raw_token), text)
        self.assertNotIn('BrandNewPass123!', text)

    def test_email_change_does_not_store_the_verification_token(self):
        _, raw_token = EmailVerification.issue(
            self.other, EmailVerification.Purpose.EMAIL_CHANGE, new_email='fresh@test.com'
        )
        self.client.force_authenticate(None)

        with patch('accounts.views.send_email_change_notice'):
            response = self.client.get(f'/api/accounts/verify-email-change/{raw_token}/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='email_change').exists())
        text = self.all_text()
        self.assertNotIn(raw_token, text)
        self.assertNotIn(EmailVerification.hash_token(raw_token), text)

    def test_api_response_contains_no_secret_fields(self):
        self.make_entry()

        body = self.client.get(URL).content.decode().lower()

        for word in ('password"', 'token'):
            self.assertNotIn(word, body)