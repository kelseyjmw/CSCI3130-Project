from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import LoginFailure


def get_client_ip(request):
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def recent_failures(ip):
    start = timezone.now() - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES)
    return LoginFailure.objects.filter(ip_address=ip, created_at__gt=start)


def check_login_allowed(ip):
    with transaction.atomic():
        failures = recent_failures(ip).select_for_update()
        if failures.count() >= settings.RATE_LIMIT_MAX_FAILURES:
            oldest = failures.order_by("created_at").first()
            retry_at = oldest.created_at + timedelta(
                minutes=settings.RATE_LIMIT_WINDOW_MINUTES
            )
            return False, retry_at
        return True, None


def record_login_failure(ip):
    LoginFailure.objects.create(ip_address=ip)
