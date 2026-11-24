from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient
from catalog.models import Category, CategoryAttribute, Listing, ListingStateChange
from security.models import Role
from tests.catalog.helpers import CatalogAPITestCase, image_upload


class ListingStateTests(CatalogAPITestCase):
    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name="Test leaf")
        self.listing.title = "Working laptop"
        self.listing.description = "Fully working laptop for sale."
        self.listing.category = self.category
        self.listing.condition = Listing.Condition.NEW
        self.listing.price = Decimal("20.00")
        self.listing.currency = "CAD"
        self.listing.quantity = 2
        self.listing.country = "CA"
        self.listing.postal_code = "generic postal code"
        self.listing.save()
        response = self.client.post(self.images, {"file": image_upload()}, format="multipart")
        self.assertEqual(response.status_code, 201)

    def action(self, name):
        return self.client.post(f"{self.detail}{name}/", {}, format="json")

    def test_valid_draft_publishes_immediately_and_records_actor_and_dates(self):
        Listing.objects.filter(pk=self.listing.pk).update(updated_at=timezone.now() - timedelta(seconds=1))
        previous = Listing.objects.get(pk=self.listing.pk).updated_at
        response = self.action("publish")
        self.assertEqual(response.status_code, 200, response.data)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.state, Listing.State.ACTIVE)
        self.assertIsNotNone(self.listing.published_at)
        self.assertGreater(self.listing.updated_at, previous)
        change = self.listing.state_changes.get()
        self.assertEqual(change.actor, self.seller)
        self.assertEqual(change.old_state, Listing.State.DRAFT)
        self.assertEqual(change.new_state, Listing.State.ACTIVE)
        self.assertGreaterEqual(change.changed_at, self.listing.published_at)

    def test_country_and_currency_accept_iso_codes_and_normalize_case(self):
        response = self.client.patch(self.detail, {"country": "br", "currency": "brl"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["country"], "BR")
        self.assertEqual(response.data["currency"], "BRL")
        self.assertEqual(self.action("publish").status_code, 200)

    def test_unknown_iso_codes_are_rejected_even_in_drafts(self):
        for field, value in (("country", "ZZ"), ("currency", "QQQ")):
            response = self.client.patch(self.detail, {field: value}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.data)

    def test_model_validation_also_checks_iso_codes(self):
        for field, value in (("country", "ZZ"), ("currency", "QQQ")):
            original = getattr(self.listing, field)
            setattr(self.listing, field, value)
            with self.assertRaises(ValidationError):
                self.listing.full_clean()
            setattr(self.listing, field, original)

    def test_required_fields_must_be_present_before_publication(self):
        for field, empty in {
            "title": "", "description": "", "category": None, "condition": "",
            "price": None, "currency": "", "quantity": None, "country": "", "postal_code": "   ",
        }.items():
            with self.subTest(field=field):
                original = getattr(self.listing, field)
                Listing.objects.filter(pk=self.listing.pk).update(**{field: empty})
                response = self.action("publish")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
                self.assertFalse(self.listing.state_changes.exists())
                Listing.objects.filter(pk=self.listing.pk).update(**{field: original})

    def test_publication_revalidates_saved_fields_instead_of_trusting_draft_writes(self):
        for field, invalid in (
            ("title", "x" * 9), ("title", "x" * 81),
            ("description", "x" * 19), ("description", "x" * 5001),
            ("price", Decimal("0")), ("quantity", 0), ("country", "ZZ"),
            ("currency", "QQQ"), ("condition", "invalid"), ("postal_code", "x" * 21),
        ):
            with self.subTest(field=field, invalid=invalid):
                original = getattr(self.listing, field)
                Listing.objects.filter(pk=self.listing.pk).update(**{field: invalid})
                response = self.action("publish")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
                Listing.objects.filter(pk=self.listing.pk).update(**{field: original})

    def test_publication_accepts_boundary_lengths_and_generic_postal_code(self):
        Listing.objects.filter(pk=self.listing.pk).update(
            title="x" * 80, description="x" * 5000, postal_code="anything!",
        )
        self.assertEqual(self.action("publish").status_code, 200)

    def test_category_must_still_be_a_leaf_at_publication(self):
        Category.objects.create(name="New child", parent=self.category)
        response = self.action("publish")
        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data)

    def test_end_time_is_optional_but_must_be_strictly_after_publication(self):
        now = timezone.now()
        for end_time in (now - timedelta(seconds=1), now):
            Listing.objects.filter(pk=self.listing.pk).update(ends_at=end_time)
            with patch("catalog.services.timezone.now", return_value=now):
                response = self.action("publish")
            self.assertEqual(response.status_code, 400)
            self.assertIn("ends_at", response.data)
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=now + timedelta(hours=1))
        self.assertEqual(self.action("publish").status_code, 200)

    def test_publication_requires_one_to_five_images(self):
        self.listing.images.all().delete()
        response = self.action("publish")
        self.assertEqual(response.status_code, 400)
        self.assertIn("images", response.data)
        self.listing.images.bulk_create([
            self.listing.images.model(listing=self.listing, file=f"test-{n}.png") for n in range(6)
        ])
        response = self.action("publish")
        self.assertEqual(response.status_code, 400)
        self.assertIn("images", response.data)

    def test_required_attributes_are_checked_and_numeric_zero_is_valid(self):
        CategoryAttribute.objects.create(
            category=self.category, name="Brand", code="test_brand", type="text", required=True,
        )
        CategoryAttribute.objects.create(
            category=self.category, name="Storage", code="test_storage", type="number",
            required=True, min_value=0, max_value=1024,
        )
        CategoryAttribute.objects.create(
            category=self.category, name="Color", code="test_color", type="choice",
            required=True, options=["red", "blue"],
        )
        response = self.action("publish")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data["attribute_values"]), {"test_brand", "test_storage", "test_color"})
        for invalid in (
            {"test_brand": "   ", "test_storage": 0, "test_color": "red"},
            {"test_brand": "Example", "test_storage": -1, "test_color": "red"},
            {"test_brand": "Example", "test_storage": 0, "test_color": "green"},
        ):
            Listing.objects.filter(pk=self.listing.pk).update(attribute_values=invalid)
            response = self.action("publish")
            self.assertEqual(response.status_code, 400)
            self.assertIn("attribute_values", response.data)
        Listing.objects.filter(pk=self.listing.pk).update(attribute_values={
            "test_brand": "Example", "test_storage": 0, "test_color": "red",
        })
        self.assertEqual(self.action("publish").status_code, 200)

    def test_owner_can_pause_resume_and_end_with_ordered_history(self):
        for action in ("publish", "pause", "resume", "end"):
            response = self.action(action)
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(self.listing.state_changes.values_list("new_state", flat=True)), [
            "active", "paused", "active", "ended",
        ])
        self.assertTrue(all(change.actor_id == self.seller.pk for change in self.listing.state_changes.all()))

    def test_repeated_actions_do_not_duplicate_history_or_reset_dates(self):
        for action in ("publish", "pause", "resume", "end"):
            self.assertEqual(self.action(action).status_code, 200)
            self.listing.refresh_from_db()
            count = self.listing.state_changes.count()
            updated_at = self.listing.updated_at
            published_at = self.listing.published_at
            self.assertEqual(self.action(action).status_code, 200)
            self.listing.refresh_from_db()
            self.assertEqual(self.listing.state_changes.count(), count)
            self.assertEqual(self.listing.updated_at, updated_at)
            self.assertEqual(self.listing.published_at, published_at)

    def test_invalid_source_states_are_rejected(self):
        for action in ("pause", "resume", "end"):
            self.assertEqual(self.action(action).status_code, 400)
        self.assertEqual(self.action("publish").status_code, 200)
        self.assertEqual(self.action("pause").status_code, 200)
        self.assertEqual(self.action("publish").status_code, 400)
        for state in (Listing.State.SOLD_OUT, Listing.State.ENDED, Listing.State.REMOVED):
            Listing.objects.filter(pk=self.listing.pk).update(state=state)
            for action in ("publish", "pause", "resume"):
                self.assertEqual(self.action(action).status_code, 400)

    def test_resume_requires_stock_and_unexpired_end_time(self):
        self.action("publish")
        self.action("pause")
        for quantity in (0, None):
            Listing.objects.filter(pk=self.listing.pk).update(quantity=quantity, state=Listing.State.PAUSED)
            response = self.action("resume")
            self.assertEqual(response.status_code, 400)
            self.assertIn("state" if quantity == 0 else "quantity", response.data)
        Listing.objects.filter(pk=self.listing.pk).update(state=Listing.State.PAUSED, quantity=1, ends_at=timezone.now() - timedelta(seconds=1))
        response = self.action("resume")
        self.assertEqual(response.status_code, 400)
        self.assertIn("state", response.data)
        self.assertEqual(self.listing.state_changes.count(), 4)
        self.assertIsNone(self.listing.state_changes.last().actor)

    def test_other_seller_cannot_change_any_state(self):
        self.client.force_authenticate(self.other)
        for action in ("publish", "pause", "resume", "end", "remove"):
            self.assertEqual(self.action(action).status_code, 403)
        self.assertFalse(self.listing.state_changes.exists())

    def test_seller_cannot_remove_and_moderator_cannot_publish_for_owner(self):
        self.assertEqual(self.action("remove").status_code, 403)
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.action("publish").status_code, 403)
        self.assertEqual(self.action("pause").status_code, 403)

    def test_moderator_and_administrator_can_remove_without_deleting(self):
        for role_name in ("Moderator", "Administrator"):
            Listing.objects.filter(pk=self.listing.pk).update(state=Listing.State.DRAFT)
            Role.objects.get(name=role_name).users.add(self.moderator)
            self.client.force_authenticate(self.moderator)
            response = self.action("remove")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(Listing.objects.filter(pk=self.listing.pk, state=Listing.State.REMOVED).exists())
            self.assertEqual(self.listing.images.count(), 1)
            count = self.listing.state_changes.count()
            self.assertEqual(self.action("remove").status_code, 200)
            self.assertEqual(self.listing.state_changes.count(), count)

    def test_moderator_can_remove_a_listing_in_every_state(self):
        self.client.force_authenticate(self.moderator)
        for state in Listing.State.values:
            Listing.objects.filter(pk=self.listing.pk).update(state=state)
            self.assertEqual(self.action("remove").status_code, 200)

    def test_suspended_account_cannot_publish_or_resume_but_can_pause_and_end(self):
        type(self.seller).objects.filter(pk=self.seller.pk).update(account_state="Suspended")
        self.assertEqual(self.action("publish").status_code, 403)
        Listing.objects.filter(pk=self.listing.pk).update(state=Listing.State.PAUSED)
        self.assertEqual(self.action("resume").status_code, 403)
        Listing.objects.filter(pk=self.listing.pk).update(state=Listing.State.ACTIVE)
        self.assertEqual(self.action("pause").status_code, 200)
        self.assertEqual(self.action("end").status_code, 200)

    def test_service_rechecks_email_and_roles_from_database(self):
        type(self.seller).objects.filter(pk=self.seller.pk).update(email_verified=False)
        self.assertEqual(self.action("publish").status_code, 403)
        type(self.seller).objects.filter(pk=self.seller.pk).update(email_verified=True)
        Role.objects.get(name="Seller").users.remove(self.seller)
        self.assertEqual(self.action("publish").status_code, 403)

    def test_action_payload_cannot_edit_fields_or_supply_actor(self):
        response = self.client.post(self.detail + "publish/", {"actor": self.other.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.listing.state_changes.exists())

    def test_state_and_publication_date_roll_back_if_history_cannot_be_saved(self):
        self.listing.refresh_from_db()
        original_update = self.listing.updated_at
        with patch("catalog.services.ListingStateChange.objects.create", side_effect=RuntimeError("history unavailable")):
            with self.assertRaises(RuntimeError):
                self.action("publish")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.state, Listing.State.DRAFT)
        self.assertIsNone(self.listing.published_at)
        self.assertEqual(self.listing.updated_at, original_update)
        self.assertFalse(ListingStateChange.objects.filter(listing=self.listing).exists())

    def test_listing_instance_and_bulk_deletion_are_refused(self):
        with self.assertRaises(ValidationError):
            self.listing.delete()
        with self.assertRaises(ValidationError):
            Listing.objects.filter(pk=self.listing.pk).delete()
        self.assertEqual(self.client.delete(self.detail).status_code, 405)
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())

    def test_publication_uses_existing_session_and_csrf_protection(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.seller)
        self.assertEqual(client.post(self.detail + "publish/", {}, format="json").status_code, 403)
        token = client.get("/api/accounts/csrf/").json()["csrfToken"]
        self.assertEqual(client.post(
            self.detail + "publish/", {}, format="json", HTTP_X_CSRFTOKEN=token,
        ).status_code, 200)
