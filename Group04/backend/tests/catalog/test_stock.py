from datetime import timedelta
from io import StringIO
from django.core.management import call_command
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from catalog.models import Listing
from catalog.services import decrease_listing_stock, process_listing_states, refresh_listing_state, set_listing_stock
from tests.catalog.helpers import CatalogAPITestCase


class AutomaticListingTests(CatalogAPITestCase):
    def publish_fixture(self, **fields):
        Listing.objects.filter(pk=self.listing.pk).update(
            state=Listing.State.ACTIVE, quantity=2, published_at=timezone.now() - timedelta(hours=1), **fields,
        )

    def test_zero_stock_wins_over_simultaneous_expiration(self):
        self.publish_fixture(ends_at=timezone.now() - timedelta(seconds=1))
        listing = set_listing_stock(self.listing.pk, 0)
        self.assertEqual(listing.state, Listing.State.SOLD_OUT)
        change = listing.state_changes.get()
        self.assertIsNone(change.actor)
        self.assertEqual(change.old_state, Listing.State.ACTIVE)
        self.assertEqual(change.new_state, Listing.State.SOLD_OUT)
        process_listing_states()
        self.assertEqual(listing.state_changes.count(), 1)

    def test_only_active_and_paused_expire(self):
        for state in Listing.State.values:
            Listing.objects.filter(pk=self.listing.pk).update(
                state=state, quantity=1, ends_at=timezone.now() - timedelta(seconds=1),
            )
            listing = refresh_listing_state(self.listing.pk)
            expected = Listing.State.ENDED if state in ("active", "paused") else state
            self.assertEqual(listing.state, expected)

    def test_no_end_time_and_future_end_time_do_not_expire(self):
        for ends_at in (None, timezone.now() + timedelta(days=1)):
            self.publish_fixture(ends_at=ends_at)
            self.assertEqual(refresh_listing_state(self.listing.pk).state, Listing.State.ACTIVE)
        self.assertFalse(self.listing.state_changes.exists())

    def test_drafts_and_removed_listings_are_preserved_at_zero_stock(self):
        for state in (Listing.State.DRAFT, Listing.State.REMOVED):
            Listing.objects.filter(pk=self.listing.pk).update(state=state, quantity=0, ends_at=timezone.now() - timedelta(days=1))
            self.assertEqual(refresh_listing_state(self.listing.pk).state, state)
        self.assertFalse(self.listing.state_changes.exists())

    def test_sold_out_is_not_reactivated_after_restocking(self):
        self.publish_fixture()
        set_listing_stock(self.listing.pk, 0)
        self.assertEqual(set_listing_stock(self.listing.pk, 5).state, Listing.State.SOLD_OUT)

    def test_stock_never_becomes_negative_or_fractional(self):
        self.publish_fixture()
        for invalid in (-1, 0.5, True, None):
            with self.assertRaises(ValidationError):
                set_listing_stock(self.listing.pk, invalid)
        with self.assertRaises(ValidationError):
            decrease_listing_stock(self.listing.pk, 3)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 2)

    def test_purchase_decrease_can_exhaust_stock(self):
        self.publish_fixture()
        listing = decrease_listing_stock(self.listing.pk, 2)
        self.assertEqual(listing.quantity, 0)
        self.assertEqual(listing.state, Listing.State.SOLD_OUT)
        self.assertIsNone(listing.state_changes.get().actor)

    def test_expired_or_suspended_listing_cannot_sell_before_worker_runs(self):
        self.publish_fixture(ends_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            decrease_listing_stock(self.listing.pk, 1)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 2)
        self.assertEqual(self.listing.state, Listing.State.ENDED)
        self.publish_fixture(ends_at=None)
        type(self.seller).objects.filter(pk=self.seller.pk).update(account_state="Suspended")
        with self.assertRaises(ValidationError):
            decrease_listing_stock(self.listing.pk, 1)

    def test_command_is_repeatable_and_records_system(self):
        self.publish_fixture(ends_at=timezone.now() - timedelta(seconds=1))
        for _ in range(2):
            call_command("process_listings", stdout=StringIO())
        self.assertEqual(self.listing.state_changes.count(), 1)
        self.assertIsNone(self.listing.state_changes.get().actor)
