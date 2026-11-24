from django.db import transaction
from rest_framework.exceptions import ValidationError
from catalog.models import Category
from catalog.services import decrease_listing_stock, update_listing_details
from tests.catalog.helpers import CatalogAPITestCase


class PublishedEditTests(CatalogAPITestCase):
    def setUp(self):
        super().setUp()
        category = Category.objects.create(name="Public leaf")
        response = self.client.patch(self.detail, {
            "title": "Published listing", "description": "A complete listing for editing tests.",
            "category": category.pk, "condition": "new", "price": "10.00", "currency": "CAD",
            "quantity": 2, "country": "CA", "postal_code": "generic",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.upload().status_code, 201)
        self.assertEqual(self.client.post(self.detail + "publish/", {}, format="json").status_code, 200)

    def test_editing_stock_to_zero_marks_published_listing_sold_out(self):
        response = self.client.patch(self.detail, {"quantity": 0}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], "sold_out")
        self.assertIsNone(self.listing.state_changes.last().actor)

    def test_published_details_cannot_be_made_incomplete(self):
        response = self.client.patch(self.detail, {"title": "Short"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "Published listing")

    def test_first_purchase_locks_details_and_only_allows_stock_increases(self):
        purchased = decrease_listing_stock(self.listing.pk, 1)
        self.assertTrue(purchased.details_locked)
        for data in ({"title": "Changed title"}, {"quantity": 0}, {"quantity": 1}, {"quantity": 3, "title": "Changed title"}):
            with self.subTest(data=data):
                self.assertEqual(self.client.patch(self.detail, data, format="json").status_code, 400)
        with self.assertRaises(ValidationError):
            update_listing_details(self.listing.pk, {"description": "A prohibited direct service edit."})
        response = self.client.patch(self.detail, {"quantity": 3}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["details_locked"])
        self.assertEqual(response.data["quantity"], 3)
        self.assertEqual(response.data["title"], "Published listing")

    def test_first_purchase_blocks_all_image_edits(self):
        decrease_listing_stock(self.listing.pk, 1)
        image_id = self.listing.images.get().pk
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(self.client.patch(self.image_detail(image_id), {"description": "Changed"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(self.image_detail(image_id)).status_code, 400)
        self.assertEqual(self.client.patch(self.images + "reorder/", {"image_ids": [image_id]}, format="json").status_code, 400)
        self.assertEqual(self.listing.images.count(), 1)

    def test_lock_preserves_state_actions_moderation_and_purchase_decreases(self):
        decrease_listing_stock(self.listing.pk, 1)
        for action in ("pause", "resume"):
            self.assertEqual(self.client.post(self.detail + action + "/", {}, format="json").status_code, 200)
        self.assertEqual(decrease_listing_stock(self.listing.pk, 1).state, "sold_out")
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.post(self.detail + "remove/", {}, format="json").status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.state, "removed")
        self.assertTrue(self.listing.details_locked)

    def test_failed_order_transaction_rolls_back_stock_and_detail_lock(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                decrease_listing_stock(self.listing.pk, 1)
                raise RuntimeError("Order creation failed")
        self.listing.refresh_from_db()
        self.assertFalse(self.listing.details_locked)
        self.assertEqual(self.listing.quantity, 2)
