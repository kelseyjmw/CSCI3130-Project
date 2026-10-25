from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone
from security.models import LoginFailure


class LoginLimitTests(TestCase):
    def fail(self):
        return Client().post(
            "/api/accounts/login/",
            data='{"email":"x@test.com","password":"wrong"}',
            content_type="application/json",
            REMOTE_ADDR="127.0.0.1",
        )

    @override_settings(RATE_LIMIT_MAX_FAILURES=3, RATE_LIMIT_WINDOW_MINUTES=15)
    def test_too_many_failures(self):
        for _ in range(3):
            self.assertEqual(self.fail().status_code, 401)
        self.assertEqual(self.fail().status_code, 429)

    @override_settings(RATE_LIMIT_MAX_FAILURES=3, RATE_LIMIT_WINDOW_MINUTES=15)
    def test_old_failures_do_not_count(self):
        old = timezone.now() - timedelta(minutes=16)
        for _ in range(3):
            LoginFailure.objects.create(ip_address="127.0.0.1", created_at=old)
        self.assertEqual(self.fail().status_code, 401)

    @override_settings(RATE_LIMIT_MAX_FAILURES=3, RATE_LIMIT_WINDOW_MINUTES=15)
    def test_blocked_request_does_not_add_failure(self):
        for _ in range(3):
            self.assertEqual(self.fail().status_code, 401)
        before = LoginFailure.objects.filter(ip_address="127.0.0.1").count()
        self.assertEqual(self.fail().status_code, 429)
        self.assertEqual(
            LoginFailure.objects.filter(ip_address="127.0.0.1").count(),
            before,
        )
