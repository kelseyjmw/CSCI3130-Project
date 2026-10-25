from datetime import timedelta
from django.utils import timezone
from catalog.models import Listing
from tests.catalog.helpers import CatalogAPITestCase


class PublicCatalogTests(CatalogAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(None)

    def test_catalog_contains_only_available_listings(self):
        expected = []
        for state in Listing.State.values:
            listing = Listing.objects.create(seller=self.seller, state=state, quantity=1, currency="CAD")
            if state == "active":
                expected.append(listing.pk)
        response = self.client.get("/api/catalog/listings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], expected)

    def test_expired_listing_leaves_catalog_but_detail_remains_visible(self):
        Listing.objects.filter(pk=self.listing.pk).update(state="active", quantity=1, currency="CAD", ends_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get("/api/catalog/listings/").data["results"], [])
        response = self.client.get(self.detail)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "ended")
        self.assertFalse(response.data["is_available"])
        self.assertEqual(response.data["available_actions"], [])

    def test_suspension_hides_detail_and_images_and_reactivation_restores_visibility(self):
        self.client.force_authenticate(self.seller)
        image = self.upload().data["id"]
        self.client.force_authenticate(None)
        Listing.objects.filter(pk=self.listing.pk).update(state="active", quantity=1, currency="CAD")
        url = f"{self.images}{image}/file/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        type(self.seller).objects.filter(pk=self.seller.pk).update(account_state="Suspended")
        self.assertEqual(self.client.get("/api/catalog/listings/").data["results"], [])
        self.assertEqual(self.client.get(self.detail).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 403)
        type(self.seller).objects.filter(pk=self.seller.pk).update(account_state="Active")
        self.assertEqual(self.client.get(self.detail).status_code, 200)
