from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from catalog.models import Listing
from security.models import Role
from security.permissions import grant_seller


def image_upload(format="PNG", name="original.png", content_type="image/png", exif=None):
    buffer = BytesIO()
    image = Image.new("RGB", (3, 2), "red")
    image.save(buffer, format=format, **({"exif": exif} if exif is not None else {}))
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class CatalogAPITestCase(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory(prefix="catalog-media-", dir=settings.BASE_DIR)
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.seller = get_user_model().objects.create_user(email="api-seller@example.com", email_verified=True)
        self.other = get_user_model().objects.create_user(email="api-other@example.com", email_verified=True)
        self.moderator = get_user_model().objects.create_user(email="api-mod@example.com", email_verified=True)
        grant_seller(self.seller)
        grant_seller(self.other)
        Role.objects.get(name="Moderator").users.add(self.moderator)
        self.client = APIClient()
        self.client.force_authenticate(self.seller)
        self.listing = Listing.objects.create(seller=self.seller)
        self.detail = f"/api/catalog/listings/{self.listing.pk}/"
        self.images = self.detail + "images/"

    def upload(self, **kwargs):
        return self.client.post(self.images, {"file": image_upload(**kwargs)}, format="multipart")

    def image_detail(self, image_id):
        return f"{self.images}{image_id}/"
