from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from catalog.models import Listing, ListingImage, ListingStateChange


class ListingModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = get_user_model().objects.create_user(
            email="catalog-seller@example.com",
        )

    def test_incomplete_draft_is_valid(self):
        listing = Listing(seller=self.seller)
        listing.full_clean()
        listing.save()
        listing.refresh_from_db()

        self.assertEqual(listing.state, Listing.State.DRAFT)
        self.assertEqual(listing.title, "")
        self.assertIsNone(listing.category)
        self.assertIsNone(listing.price)
        self.assertIsNone(listing.quantity)
        self.assertIsNone(listing.ends_at)
        self.assertIsNone(listing.published_at)
        self.assertIsNotNone(listing.created_at)
        self.assertIsNotNone(listing.updated_at)
        self.assertFalse(listing.images.exists())

    def test_database_rejects_negative_stock_even_on_direct_update(self):
        listing = Listing.objects.create(seller=self.seller, quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Listing.objects.filter(pk=listing.pk).update(quantity=-1)
        listing.refresh_from_db()
        self.assertEqual(listing.quantity, 1)

    def test_zero_stock_is_allowed(self):
        listing = Listing(seller=self.seller, quantity=0)
        listing.full_clean()
        listing.save()

    def test_images_use_position_and_next_remaining_image_becomes_first(self):
        listing = Listing.objects.create(seller=self.seller)
        later = ListingImage.objects.create(
            listing=listing, file="listing_images/later.jpg", position=2,
        )
        first = ListingImage.objects.create(
            listing=listing, file="listing_images/first.jpg", position=0,
            description="Front view",
        )
        self.assertEqual(listing.images.first(), first)
        first.delete()
        self.assertEqual(listing.images.first(), later)

    def test_listing_owner_cannot_be_deleted(self):
        Listing.objects.create(seller=self.seller)
        with self.assertRaises(ProtectedError):
            self.seller.delete()

    def test_history_preserves_listing_and_actor_and_supports_system(self):
        listing = Listing.objects.create(seller=self.seller)
        actor = get_user_model().objects.create_user(email="moderator@example.com")
        change = ListingStateChange.objects.create(
            listing=listing, old_state=Listing.State.DRAFT,
            new_state=Listing.State.ACTIVE, actor=actor,
        )
        automatic = ListingStateChange.objects.create(
            listing=listing, old_state=Listing.State.ACTIVE,
            new_state=Listing.State.ENDED,
        )
        self.assertIsNotNone(change.changed_at)
        self.assertIsNone(automatic.actor)
        self.assertEqual(list(listing.state_changes.all()), [change, automatic])
        with self.assertRaises(ProtectedError):
            actor.delete()
        with self.assertRaises(ValidationError):
            listing.delete()
