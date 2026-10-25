from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import EmailVerification
from django.test import TestCase
from django.core import mail

User = get_user_model()

class EmailChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="primary@example.com",
            password="StrongPassword123!",
        )
        self.user.email_verified = True
        self.user.save()

        self.other_user = User.objects.create_user(
            email="existing@example.com",
            password="StrongPassword123!",
        )
        self.other_user.email_verified = True
        self.other_user.save()

    def test_unauthenticated_request_rejected(self):
        response = self.client.post(
            "/api/accounts/change-email/",
            {"new_email": "newaddress@example.com"},
            content_type="application/json",
        )
        self.assertIn(response.status_code, [401, 403])

    def test_request_email_change_sends_verification_link(self):
        self.client.force_login(self.user)
        mail.outbox.clear()

        response = self.client.post(
            "/api/accounts/change-email/",
            {"new_email": "newaddress@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Verification email sent to new address
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["newaddress@example.com"])

        # Old email remains active until confirmed
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "primary@example.com")

    def test_old_email_remains_usable_for_login_until_verified(self):
        self.client.force_login(self.user)
        self.client.post(
            "/api/accounts/change-email/",
            {"new_email": "newaddress@example.com"},
            content_type="application/json",
        )
        self.client.logout()

        # Login with old email succeeds
        login_response = self.client.post(
            "/api/accounts/login/",
            {"email": "primary@example.com", "password": "StrongPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)

    def test_verify_email_change_success_and_notice(self):
        _, raw_token = EmailVerification.issue(
            self.user,
            EmailVerification.Purpose.EMAIL_CHANGE,
            new_email="newaddress@example.com",
        )
        mail.outbox.clear()

        response = self.client.get(
            f"/api/accounts/verify-email-change/{raw_token}/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Database email updated to new address
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newaddress@example.com")
        self.assertTrue(self.user.email_verified)

        # Old address receives alert notification
        self.assertTrue(
            any("primary@example.com" in msg.to for msg in mail.outbox),
            "Notification email should be sent to the old address",
        )

    def test_verification_link_is_single_use(self):
        _, raw_token = EmailVerification.issue(
            self.user,
            EmailVerification.Purpose.EMAIL_CHANGE,
            new_email="newaddress@example.com",
        )

        first_response = self.client.get(
            f"/api/accounts/verify-email-change/{raw_token}/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(first_response.status_code, 200)

        # Reusing the token must fail
        second_response = self.client.get(
            f"/api/accounts/verify-email-change/{raw_token}/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(second_response.status_code, 400)

    def test_new_request_invalidates_earlier_link(self):
        _, first_token = EmailVerification.issue(
            self.user,
            EmailVerification.Purpose.EMAIL_CHANGE,
            new_email="first@example.com",
        )

        # Issuing a new change request replaces earlier tokens
        _, second_token = EmailVerification.issue(
            self.user,
            EmailVerification.Purpose.EMAIL_CHANGE,
            new_email="second@example.com",
        )

        # First token is now invalidated
        first_response = self.client.get(
            f"/api/accounts/verify-email-change/{first_token}/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(first_response.status_code, 400)

        # Second token succeeds
        second_response = self.client.get(
            f"/api/accounts/verify-email-change/{second_token}/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(second_response.status_code, 200)

    def test_duplicate_email_rejected_at_request(self):
        self.client.force_login(self.user)

        # Exact match
        response = self.client.post(
            "/api/accounts/change-email/",
            {"new_email": "existing@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        # Case/whitespace variation
        response_variation = self.client.post(
            "/api/accounts/change-email/",
            {"new_email": "  EXISTING@EXAMPLE.COM  "},
            content_type="application/json",
        )
        self.assertEqual(response_variation.status_code, 400)

    def test_expired_token_rejected(self):
        verification, raw_token = EmailVerification.issue(
            self.user,
            EmailVerification.Purpose.EMAIL_CHANGE,
            new_email="expired@example.com",
        )
        #Advance time beyond 24h TTL
        expired_time = timezone.now() + timedelta(hours=25)
        with patch("django.utils.timezone.now", return_value=expired_time):
            response = self.client.get(
                f"/api/accounts/verify-email-change/{raw_token}/",
                HTTP_ACCEPT="application/json",
            )
            self.assertEqual(response.status_code, 400)
# Migrated from test_registration.py





