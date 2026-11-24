import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from security.models import Role

User = get_user_model()


class Command(BaseCommand):
    help = "Create the first administrator. Use ADMIN_EMAIL and ADMIN_PASSWORD env vars."

    def handle(self, *args, **options):
        email = os.environ.get("ADMIN_EMAIL")
        password = os.environ.get("ADMIN_PASSWORD")
        if not email or not password:
            raise CommandError("Set ADMIN_EMAIL and ADMIN_PASSWORD in the environment.")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"is_staff": True, "is_superuser": True, "email_verified": True},
        )
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.email_verified = True
        user.save()

        role, _ = Role.objects.get_or_create(name="Administrator")
        role.users.add(user)
        self.stdout.write("Administrator ready: " + user.email)
