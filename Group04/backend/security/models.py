from django.conf import settings
from django.db import models
from django.utils import timezone


class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.code


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    permissions = models.ManyToManyField(Permission, blank=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="roles",
    )

    def __str__(self):
        return self.name


class LoginFailure(models.Model):
    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["ip_address", "created_at"]),
        ]
