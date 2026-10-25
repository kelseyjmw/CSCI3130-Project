from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.test import APIClient
from catalog.models import Category, Listing
from catalog.services import create_listing_draft
from tests.catalog.helpers import image_upload
from security.models import Permission, Role
from security.permissions import grant_seller


class ListingCreationConcurrencyTests(TransactionTestCase):
    def test_simultaneous_creation_cannot_exceed_limit(self):
        if connection.vendor == "sqlite" and "memory" in connection.settings_dict["NAME"]:
            self.skipTest("Use a file-backed test database to check SQLite writer serialization.")
        seller = get_user_model().objects.create_user(email="concurrent@example.com", email_verified=True)
        role, _ = Role.objects.get_or_create(name="Seller")
        permission, _ = Permission.objects.get_or_create(code="listings.create")
        role.permissions.add(permission)
        grant_seller(seller)
        Listing.objects.bulk_create([Listing(seller=seller) for _ in range(99)])
        barrier = Barrier(2)

        def create():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=seller.pk)
                barrier.wait(timeout=10)
                try:
                    create_listing_draft(user)
                    return 201
                except Throttled:
                    return 429
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        self.assertEqual(sorted(results), [201, 429])
        self.assertEqual(Listing.objects.filter(seller=seller).count(), 100)


class ImageConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor == "sqlite" and "memory" in connection.settings_dict["NAME"]:
            self.skipTest("Use a file-backed test database to check SQLite writer serialization.")
        media = TemporaryDirectory(prefix="catalog-media-", dir=settings.BASE_DIR)
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.seller = get_user_model().objects.create_user(email="images-race@example.com", email_verified=True)
        role, _ = Role.objects.get_or_create(name="Seller")
        permission, _ = Permission.objects.get_or_create(code="listings.edit")
        role.permissions.add(permission)
        grant_seller(self.seller)
        self.listing = Listing.objects.create(seller=self.seller)
        self.url = f"/api/catalog/listings/{self.listing.pk}/images/"

    def client_for_seller(self):
        client = APIClient()
        client.force_authenticate(self.seller)
        return client

    def concurrent_requests(self, operation):
        barrier = Barrier(2)

        def request(index):
            close_old_connections()
            try:
                client = self.client_for_seller()
                barrier.wait(timeout=10)
                return operation(client, index).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(request, range(2)))

    def test_simultaneous_uploads_cannot_exceed_five_images(self):
        client = self.client_for_seller()
        for _ in range(4):
            self.assertEqual(client.post(self.url, {"file": image_upload()}, format="multipart").status_code, 201)
        results = self.concurrent_requests(
            lambda client, _: client.post(self.url, {"file": image_upload()}, format="multipart"),
        )
        self.assertEqual(results, [201, 400])
        self.assertEqual(self.listing.images.count(), 5)

    def test_simultaneous_deletions_keep_a_published_image(self):
        client = self.client_for_seller()
        ids = [client.post(self.url, {"file": image_upload()}, format="multipart").data["id"] for _ in range(2)]
        self.listing.state = Listing.State.ACTIVE
        self.listing.save()
        results = self.concurrent_requests(lambda client, index: client.delete(f"{self.url}{ids[index]}/"))
        self.assertEqual(results, [204, 400])
        self.assertEqual(self.listing.images.count(), 1)

    def test_simultaneous_publication_writes_only_one_history_entry(self):
        for code in ("listings.create", "listings.publish"):
            permission, _ = Permission.objects.get_or_create(code=code)
            Role.objects.get(name="Seller").permissions.add(permission)
        category = Category.objects.create(name="Concurrent leaf")
        Listing.objects.filter(pk=self.listing.pk).update(
            title="Concurrent listing", description="A complete listing ready for publication.",
            category=category, condition="new", price="10.00", currency="CAD",
            quantity=1, country="CA", postal_code="generic",
        )
        self.assertEqual(self.client_for_seller().post(
            self.url, {"file": image_upload()}, format="multipart",
        ).status_code, 201)
        url = f"/api/catalog/listings/{self.listing.pk}/publish/"
        results = self.concurrent_requests(lambda client, _: client.post(url, {}, format="json"))
        self.assertEqual(results, [200, 200])
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.state, Listing.State.ACTIVE)
        self.assertIsNotNone(self.listing.published_at)
        self.assertEqual(self.listing.state_changes.count(), 1)

    def test_simultaneous_stock_decreases_cannot_oversell(self):
        from rest_framework.exceptions import ValidationError
        from rest_framework.response import Response
        from catalog.services import decrease_listing_stock

        Listing.objects.filter(pk=self.listing.pk).update(state=Listing.State.ACTIVE, quantity=1)

        def purchase(client, index):
            try:
                decrease_listing_stock(self.listing.pk, 1)
                return Response(status=200)
            except ValidationError:
                return Response(status=400)

        self.assertEqual(self.concurrent_requests(purchase), [200, 400])
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)
        self.assertEqual(self.listing.state, Listing.State.SOLD_OUT)
        self.assertEqual(self.listing.state_changes.count(), 1)

    def test_concurrent_removal_cannot_be_undone_by_resuming(self):
        for code in ("listings.create", "listings.publish"):
            permission, _ = Permission.objects.get_or_create(code=code)
            Role.objects.get(name="Seller").permissions.add(permission)
        moderator = get_user_model().objects.create_user(email="race-mod@example.com", email_verified=True)
        role, _ = Role.objects.get_or_create(name="Moderator")
        remove, _ = Permission.objects.get_or_create(code="listings.remove")
        role.permissions.add(remove)
        role.users.add(moderator)
        Listing.objects.filter(pk=self.listing.pk).update(state=Listing.State.PAUSED, quantity=1)

        def change(client, index):
            if index:
                client.force_authenticate(moderator)
            action = "remove" if index else "resume"
            return client.post(f"/api/catalog/listings/{self.listing.pk}/{action}/", {}, format="json")

        results = self.concurrent_requests(change)
        self.assertIn(200, results)
        self.assertTrue(all(status in (200, 400) for status in results))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.state, Listing.State.REMOVED)
        self.assertEqual(self.listing.state_changes.last().new_state, Listing.State.REMOVED)
