from django.conf import settings
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import PasswordResetToken, TwoFactorRecoveryCode, User
from accounts.two_factor import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    hash_recovery_code,
    totp_code,
    verify_totp,
)
from security.models import Role


LOGIN_URL = "/api/accounts/login/"


@override_settings(SECRET_KEY="test-secret-key-for-two-factor-tests")
class TwoFactorTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            "member@example.com",
            "CorrectPassword123!",
            email_verified=True,
        )

    def test_totp_matches_rfc_6238_sha1_test_vector(self):
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

        self.assertEqual(totp_code(secret, timestamp=59), "287082")
        self.assertTrue(verify_totp(secret, "287082", timestamp=59))

    def login(self, email=None, password="CorrectPassword123!"):
        return self.client.post(
            LOGIN_URL,
            {"email": email or self.user.email, "password": password},
            format="json",
        )

    def enable_two_factor(self, user=None):
        user = user or self.user
        secret = "JBSWY3DPEHPK3PXP"
        user.totp_secret_encrypted = encrypt_totp_secret(secret)
        user.totp_enabled = True
        user.save(update_fields=["totp_secret_encrypted", "totp_enabled"])
        return secret

    def test_user_without_two_factor_keeps_password_only_login(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("mfa_required", response.json())
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 200)

    def test_enabled_user_must_complete_totp_before_session_login(self):
        secret = self.enable_two_factor()

        challenge = self.login()

        self.assertEqual(challenge.status_code, 200)
        self.assertTrue(challenge.json()["mfa_required"])
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 403)

        rejected = self.client.post(
            "/api/accounts/login/verify-mfa/",
            {"code": "not-a-code"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 403)

        response = self.client.post(
            "/api/accounts/login/verify-mfa/",
            {"code": totp_code(secret)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 200)
        self.assertEqual(self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE)
        self.assertNotIn('mfa_pending_user_id', self.client.session)

    def test_password_only_login_after_a_challenge_clears_its_short_expiry(self):
        self.enable_two_factor()
        self.assertTrue(self.login().json()['mfa_required'])
        other = User.objects.create_user('other-login@example.com', 'CorrectPassword123!', email_verified=True)

        self.assertEqual(self.login(email=other.email).status_code, 200)

        self.assertEqual(self.client.get('/api/accounts/me/').json()['id'], other.pk)
        self.assertEqual(self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE)
        self.assertNotIn('mfa_pending_user_id', self.client.session)

    def test_password_reset_invalidates_pending_totp_and_admin_enrollment(self):
        for enrollment in (False, True):
            with self.subTest(enrollment=enrollment):
                user = User.objects.create_user(
                    f'pending-{enrollment}@example.com', 'CorrectPassword123!', email_verified=True,
                )
                client = APIClient()
                if enrollment:
                    Role.objects.get_or_create(name='Administrator')[0].users.add(user)
                else:
                    secret = self.enable_two_factor(user)
                challenge = client.post(LOGIN_URL, {
                    'email': user.email, 'password': 'CorrectPassword123!',
                }, format='json')
                self.assertEqual(challenge.status_code, 200)
                if enrollment:
                    secret = client.post('/api/accounts/two-factor/setup/', {}, format='json').json()['secret']
                _, token = PasswordResetToken.issue(user)
                reset = APIClient().post(f'/api/accounts/password-reset/{token}/', {
                    'password': 'NewPassword123!',
                }, format='json')
                self.assertEqual(reset.status_code, 200)

                path = '/api/accounts/two-factor/confirm/' if enrollment else '/api/accounts/login/verify-mfa/'
                response = client.post(path, {'code': totp_code(secret)}, format='json')

                self.assertEqual(response.status_code, 401)
                self.assertEqual(client.get('/api/accounts/me/').status_code, 403)
                self.assertNotIn('mfa_pending_user_id', client.session)

    def test_password_change_invalidates_pending_mfa_and_keeps_current_session(self):
        secret = self.enable_two_factor()
        self.assertTrue(self.login().json()['mfa_required'])
        current = APIClient()
        current.force_login(self.user)

        changed = current.post('/api/accounts/password/change/', {
            'current_password': 'CorrectPassword123!', 'new_password': 'NewPassword123!',
        }, format='json')

        self.assertEqual(changed.status_code, 200)
        self.assertEqual(current.get('/api/accounts/me/').status_code, 200)
        response = self.client.post('/api/accounts/login/verify-mfa/', {
            'code': totp_code(secret),
        }, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get('/api/accounts/me/').status_code, 403)

    def test_login_requires_csrf_and_accepts_token_from_csrf_endpoint(self):
        client = Client(enforce_csrf_checks=True)
        denied = client.post(
            LOGIN_URL,
            {"email": self.user.email, "password": "CorrectPassword123!"},
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

        csrf_token = client.get("/api/accounts/csrf/").json()["csrfToken"]
        response = client.post(
            LOGIN_URL,
            {"email": self.user.email, "password": "CorrectPassword123!"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)

    def test_recovery_code_is_consumed_once(self):
        self.enable_two_factor()
        recovery_code = generate_recovery_codes()[0]
        TwoFactorRecoveryCode.objects.create(
            user=self.user,
            code_hash=hash_recovery_code(recovery_code),
        )

        self.assertTrue(self.login().json()["mfa_required"])
        first_use = self.client.post(
            "/api/accounts/login/verify-mfa/",
            {"recovery_code": recovery_code.lower()},
            format="json",
        )
        self.assertEqual(first_use.status_code, 200)
        self.client.post("/api/accounts/logout/")

        self.assertTrue(self.login().json()["mfa_required"])
        second_use = self.client.post(
            "/api/accounts/login/verify-mfa/",
            {"recovery_code": recovery_code},
            format="json",
        )

        self.assertEqual(second_use.status_code, 401)
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 403)

    def test_admin_must_enroll_before_receiving_authenticated_session(self):
        role, _ = Role.objects.get_or_create(name="Administrator")
        role.users.add(self.user)

        challenge = self.login()

        self.assertTrue(challenge.json()["enrollment_required"])
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 403)

        setup = self.client.post("/api/accounts/two-factor/setup/", {}, format="json")
        self.assertEqual(setup.status_code, 200)
        self.assertEqual(
            decrypt_totp_secret(self.user.__class__.objects.get(pk=self.user.pk).totp_secret_encrypted),
            setup.json()["secret"],
        )

        confirmation = self.client.post(
            "/api/accounts/two-factor/confirm/",
            {"code": totp_code(setup.json()["secret"])},
            format="json",
        )

        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(len(confirmation.json()["recovery_codes"]), 10)
        self.assertTrue(self.client.get("/api/accounts/me/").json()["totp_enabled"])
        self.assertEqual(
            TwoFactorRecoveryCode.objects.filter(user=self.user, used_at__isnull=True).count(),
            10,
        )

    def test_regular_user_can_enable_two_factor_after_password_confirmation(self):
        self.login()
        rejected = self.client.post(
            "/api/accounts/two-factor/setup/",
            {"password": "incorrect"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 401)
        self.assertFalse(User.objects.get(pk=self.user.pk).totp_enabled)

        setup = self.client.post(
            "/api/accounts/two-factor/setup/",
            {"password": "CorrectPassword123!"},
            format="json",
        )
        self.assertEqual(setup.status_code, 200)

        confirmation = self.client.post(
            "/api/accounts/two-factor/confirm/",
            {"code": totp_code(setup.json()["secret"])},
            format="json",
        )

        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(len(confirmation.json()["recovery_codes"]), 10)
        self.assertTrue(User.objects.get(pk=self.user.pk).totp_enabled)

    def test_recovery_codes_are_not_stored_in_plaintext(self):
        role, _ = Role.objects.get_or_create(name="Administrator")
        role.users.add(self.user)
        self.login()
        setup = self.client.post("/api/accounts/two-factor/setup/", {}, format="json")
        response = self.client.post(
            "/api/accounts/two-factor/confirm/",
            {"code": totp_code(setup.json()["secret"])},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        stored_hashes = set(
            TwoFactorRecoveryCode.objects.filter(user=self.user).values_list("code_hash", flat=True)
        )
        self.assertEqual(len(stored_hashes), 10)
        self.assertTrue(
            all(hash_recovery_code(code) in stored_hashes for code in response.json()["recovery_codes"])
        )
        self.assertTrue(
            all(code not in stored_hashes for code in response.json()["recovery_codes"])
        )

    def test_login_challenge_expires(self):
        self.enable_two_factor()
        self.assertTrue(self.login().json()["mfa_required"])
        session = self.client.session
        session["mfa_pending_expires_at"] = 1
        session.save()

        response = self.client.post(
            "/api/accounts/login/verify-mfa/",
            {"code": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_admin_promotion_invalidates_password_only_access(self):
        self.assertEqual(self.login().status_code, 200)
        role, _ = Role.objects.get_or_create(name="Administrator")
        role.users.add(self.user)

        blocked = self.client.get("/api/accounts/me/")

        self.assertEqual(blocked.status_code, 403)
        self.assertTrue(self.login().json()["enrollment_required"])

    def test_staff_account_is_also_required_to_enroll(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.login()

        self.assertTrue(response.json()["enrollment_required"])
