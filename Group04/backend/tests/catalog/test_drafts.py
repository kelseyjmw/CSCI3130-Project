from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from catalog.models import Category, Listing
from tests.catalog.helpers import CatalogAPITestCase


class DraftAPITests(CatalogAPITestCase):
    def test_empty_and_partial_drafts_can_be_created_and_reopened(self):
        response = self.client.post("/api/catalog/listings/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["seller"], self.seller.pk)
        self.assertEqual(response.data["state"], "draft")
        self.assertEqual(response.data["images"], [])
        detail = f'/api/catalog/listings/{response.data["id"]}/'
        response = self.client.patch(detail, {"title": "Laptop", "price": "20.50"}, format="json")
        self.assertEqual(response.status_code, 200)
        reopened = self.client.get(detail)
        self.assertEqual(reopened.data["title"], "Laptop")
        self.assertEqual(reopened.data["price"], "20.50")
        self.assertIsNone(reopened.data["category"])

    def test_listing_own_drafts_does_not_expose_other_sellers(self):
        other = Listing.objects.create(seller=self.other)
        response = self.client.get("/api/catalog/listings/mine/")
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.listing.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_protected_and_unknown_fields_are_rejected(self):
        for field, value in {
            "seller": self.other.pk, "state": "active", "published_at": timezone.now().isoformat(),
            "images": [], "unexpected": "value",
        }.items():
            with self.subTest(field=field):
                response = self.client.patch(self.detail, {field: value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.seller, self.seller)
        self.assertEqual(self.listing.state, Listing.State.DRAFT)

    def test_invalid_supplied_values_are_rejected_without_changing_draft(self):
        for field, value in {
            "price": "0", "quantity": -1, "currency": "INVALID", "condition": "broken",
            "title": "x" * 81, "description": "x" * 5001, "country": "Canada",
            "ends_at": "not-a-date", "attribute_values": ["not-a-dict"],
        }.items():
            with self.subTest(field=field):
                response = self.client.patch(self.detail, {field: value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_leaf_category_and_attribute_types_and_ranges_are_validated(self):
        call_command("seed_catalog", stdout=StringIO())
        laptops = Category.objects.get(name="Laptops")
        parent = Category.objects.get(name="Computers")
        response = self.client.patch(self.detail, {"category": parent.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(self.detail, {"category": laptops.pk}, format="json")
        self.assertEqual(response.status_code, 200)  # Required attributes can be absent in drafts.
        for attributes in (
            {"laptop_brand": 123}, {"laptop_memory_gb": -1}, {"laptop_memory_gb": 1025},
            {"laptop_memory_gb": "NaN"}, {"laptop_memory_gb": True}, {"foreign_code": "x"},
        ):
            with self.subTest(attributes=attributes):
                response = self.client.patch(self.detail, {"attribute_values": attributes}, format="json")
                self.assertEqual(response.status_code, 400)
        chairs = Category.objects.get(name="Chairs")
        response = self.client.patch(self.detail, {
            "category": chairs.pk, "attribute_values": {"chair_material": "invalid"},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(self.detail, {
            "attribute_values": {"laptop_brand": "Example", "laptop_memory_gb": 16},
        }, format="json")
        self.assertEqual(response.status_code, 200)

    def test_creation_limit_returns_429_and_retry_header(self):
        Listing.objects.bulk_create([Listing(seller=self.seller) for _ in range(99)])
        response = self.client.post("/api/catalog/listings/", {}, format="json")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertEqual(self.seller.listings.count(), 100)

    def test_non_seller_and_unverified_and_anonymous_creation_is_denied(self):
        buyer = get_user_model().objects.create_user(email="api-buyer@example.com", email_verified=True)
        for user in (buyer, self.moderator, None):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.post("/api/catalog/listings/", {}, format="json").status_code, 403)
        self.seller.email_verified = False
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.post("/api/catalog/listings/", {}, format="json").status_code, 403)

    def test_other_seller_cannot_read_or_edit_draft_but_moderator_can(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.detail).status_code, 403)
        self.assertEqual(self.client.patch(self.detail, {"title": "Changed"}, format="json").status_code, 403)
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.patch(self.detail, {"title": "Changed"}, format="json").status_code, 200)

    def test_non_draft_edits_and_physical_deletion_are_unavailable(self):
        self.listing.state = Listing.State.ACTIVE
        self.listing.save()
        self.assertEqual(self.client.patch(self.detail, {"title": "Changed"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(self.detail).status_code, 405)
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())

    def test_session_writes_require_csrf_and_work_with_existing_csrf_endpoint(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.seller)
        self.assertEqual(client.post("/api/catalog/listings/", {}, format="json").status_code, 403)
        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        self.assertEqual(client.post(
            "/api/catalog/listings/", {}, format="json", HTTP_X_CSRFTOKEN=csrf,
        ).status_code, 201)

    def test_stock_outside_database_range_is_rejected(self):
        response = self.client.patch(self.detail, {"quantity": 2**63}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.data)
        self.listing.refresh_from_db()
        self.assertIsNone(self.listing.quantity)
