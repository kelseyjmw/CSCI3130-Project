from datetime import timedelta
from io import BytesIO
from pathlib import Path
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from catalog.images import MAX_IMAGE_SIZE
from catalog.models import Listing, ListingImage
from tests.catalog.helpers import CatalogAPITestCase, image_upload


class ListingImageAPITests(CatalogAPITestCase):
    def test_supported_formats_use_actual_content_and_new_names(self):
        for format, extension in (("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")):
            with self.subTest(format=format):
                response = self.upload(format=format, name="untrusted.exe", content_type="text/plain")
                self.assertEqual(response.status_code, 201)
                image = ListingImage.objects.get(pk=response.data["id"])
                self.assertNotIn("untrusted", image.file.name)
                self.assertTrue(image.file.name.endswith(extension))
                self.assertEqual(len(Path(image.file.name).stem), 32)
                with image.file.open("rb") as stream, Image.open(stream) as decoded:
                    self.assertEqual(decoded.format, format)

    def test_exif_is_removed_and_orientation_preserved_for_all_formats(self):
        for format in ("JPEG", "PNG", "WEBP"):
            with self.subTest(format=format):
                exif = Image.Exif()
                exif[315] = "Private author"
                exif[274] = 6
                response = self.upload(format=format, exif=exif)
                self.assertEqual(response.status_code, 201)
                image = ListingImage.objects.get(pk=response.data["id"])
                with image.file.open("rb") as stream, Image.open(stream) as decoded:
                    self.assertEqual(dict(decoded.getexif()), {})
                    self.assertEqual(decoded.size, (2, 3))

    def test_png_transparency_is_preserved(self):
        buffer = BytesIO()
        Image.new("RGBA", (2, 2), (255, 0, 0, 0)).save(buffer, format="PNG")
        response = self.client.post(self.images, {
            "file": SimpleUploadedFile("transparent.png", buffer.getvalue()),
        }, format="multipart")
        self.assertEqual(response.status_code, 201)
        image = ListingImage.objects.get(pk=response.data["id"])
        with image.file.open("rb") as stream, Image.open(stream) as decoded:
            self.assertEqual(decoded.getpixel((0, 0))[3], 0)

    def test_invalid_unsupported_oversized_and_external_files_are_rejected(self):
        files = [
            SimpleUploadedFile("fake.jpg", b"<script>bad()</script>", content_type="image/jpeg"),
            SimpleUploadedFile("truncated.jpg", b"\xff\xd8\xff\xe0"),
            image_upload(format="GIF"),
            SimpleUploadedFile("large.jpg", b"x" * (MAX_IMAGE_SIZE + 1)),
            "https://example.com/image.jpg",
        ]
        for upload in files:
            with self.subTest(upload=str(upload)):
                response = self.client.post(self.images, {"file": upload}, format="multipart")
                self.assertEqual(response.status_code, 400)
                self.assertIn("file", response.data)
        self.assertFalse(self.listing.images.exists())
        self.assertEqual(list(Path(self.media.name).rglob("*")), [])

    def test_only_five_images_are_allowed(self):
        for _ in range(5):
            self.assertEqual(self.upload().status_code, 201)
        response = self.upload()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.listing.images.count(), 5)
        self.assertEqual(len(list(Path(self.media.name).rglob("*.png"))), 5)

    def test_descriptions_and_order_can_be_changed_and_touch_listing_date(self):
        first = self.upload().data["id"]
        second = self.upload().data["id"]
        Listing.objects.filter(pk=self.listing.pk).update(updated_at=timezone.now() - timedelta(days=1))
        previous = Listing.objects.get(pk=self.listing.pk).updated_at
        response = self.client.patch(self.image_detail(first), {"description": "Front view"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["description"], "Front view")
        self.listing.refresh_from_db()
        self.assertGreater(self.listing.updated_at, previous)
        response = self.client.patch(self.images + "reorder/", {"image_ids": [second, first]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([image["id"] for image in response.data], [second, first])
        detail = self.client.get(self.detail)
        self.assertEqual(detail.data["images"][0]["id"], second)

    def test_invalid_reorders_do_not_change_images(self):
        first = self.upload().data["id"]
        second = self.upload().data["id"]
        other = Listing.objects.create(seller=self.other)
        foreign = ListingImage.objects.create(listing=other, file="foreign.png")
        for ids in ([first], [first, first], [first, foreign.pk], [first, second, 999999]):
            response = self.client.patch(self.images + "reorder/", {"image_ids": ids}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(self.listing.images.values_list("pk", flat=True)), [first, second])

    def test_removing_primary_promotes_next_and_deletes_stored_file(self):
        first = self.upload().data["id"]
        second = self.upload().data["id"]
        path = ListingImage.objects.get(pk=first).file.path
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(self.image_detail(first)).status_code, 204)
        self.assertFalse(Path(path).exists())
        self.assertEqual(self.listing.images.first().pk, second)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(self.image_detail(second)).status_code, 204)
        self.assertFalse(self.listing.images.exists())

    def test_published_listing_keeps_at_least_one_image(self):
        first = self.upload().data["id"]
        second = self.upload().data["id"]
        self.listing.state = Listing.State.ACTIVE
        self.listing.published_at = timezone.now()
        self.listing.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(self.image_detail(first)).status_code, 204)
        self.assertEqual(self.client.delete(self.image_detail(second)).status_code, 400)
        self.assertEqual(self.listing.images.count(), 1)

    def test_image_download_and_mutations_require_listing_permission(self):
        response = self.upload()
        image_id = response.data["id"]
        file_url = f"{self.image_detail(image_id)}file/"
        response = self.client.get(file_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"\x89PNG"))
        for user in (self.other, None):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(file_url).status_code, 403)
            self.assertEqual(self.upload().status_code, 403)
            self.assertEqual(self.client.patch(self.image_detail(image_id), {"description": "Bad"}, format="json").status_code, 403)
            self.assertEqual(self.client.delete(self.image_detail(image_id)).status_code, 403)
            self.assertEqual(self.client.patch(self.images + "reorder/", {"image_ids": [image_id]}, format="json").status_code, 403)

    def test_swapping_image_identifier_does_not_cross_listing_boundaries(self):
        other_listing = Listing.objects.create(seller=self.seller)
        foreign = ListingImage.objects.create(listing=other_listing, file="foreign.png")
        self.assertEqual(self.client.patch(self.image_detail(foreign.pk), {"description": "Bad"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.image_detail(foreign.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.image_detail(foreign.pk) + "file/").status_code, 404)

    def test_image_replacement_or_direct_position_edit_is_rejected(self):
        image_id = self.upload().data["id"]
        for data in ({"description": "x", "file": "https://example.com/x.jpg"}, {"description": "x", "position": 2}):
            response = self.client.patch(self.image_detail(image_id), data, format="json")
            self.assertEqual(response.status_code, 400)

    def test_removed_listing_rejects_image_mutations(self):
        image_id = self.upload().data["id"]
        self.listing.state = Listing.State.REMOVED
        self.listing.save()
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(self.client.delete(self.image_detail(image_id)).status_code, 400)
        self.assertEqual(self.client.patch(self.images + "reorder/", {"image_ids": [image_id]}, format="json").status_code, 400)
