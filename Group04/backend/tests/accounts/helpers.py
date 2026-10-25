from datetime import timedelta
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User, SellerApplication
from security.models import Role


BASE = '/api/accounts/seller-applications'


def has_role(user, name):
    return Role.objects.filter(name=name, users=user).exists()


def add_role(user, name):
    role, _ = Role.objects.get_or_create(name=name)
    role.users.add(user)


def rows(response):
    """Works whether or not the list endpoint is paginated."""
    data = response.data
    return data['results'] if isinstance(data, dict) and 'results' in data else data


class ReviewTestBase(TestCase):
    def setUp(self):
        media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(media_dir.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media_dir.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        self.moderator = User.objects.create_user('mod@test.com', 'password')
        self.admin = User.objects.create_user('admin@test.com', 'password')
        self.applicant = User.objects.create_user('applicant@test.com', 'password')
        self.other = User.objects.create_user('other@test.com', 'password')

        add_role(self.moderator, 'Moderator')
        add_role(self.admin, 'Administrator')

        self.client = APIClient()
        self.client.force_authenticate(self.moderator)

    def make_application(self, applicant=None, status=SellerApplication.Status.PENDING,
                         hours_since_review=None):
        application = SellerApplication.objects.create(
            applicant=applicant or self.applicant,
            applicant_type='person',
            identity_document_image='id.png',
            status=status,
        )
        if hours_since_review is not None:
            SellerApplication.objects.filter(pk=application.pk).update(
                reviewed_at=timezone.now() - timedelta(hours=hours_since_review)
            )
            application.refresh_from_db()
        return application

    def approve(self, application):
        return self.client.post(f'{BASE}/{application.pk}/approve/')

    def reject(self, application, reason='Document is unreadable.'):
        return self.client.post(
            f'{BASE}/{application.pk}/reject/', {'reason': reason}, format='json'
        )

    def image_file(self):
        return SimpleUploadedFile(
            'identity.png',
            b'\x89PNG\r\n\x1a\n' + b'\x00' * 16,
            content_type='image/png',
        )

    def apply(self):
        return self.client.post(
            f'{BASE}/',
            {'applicant_type': 'person', 'identity_document_image': self.image_file()},
            format='multipart',
        )
