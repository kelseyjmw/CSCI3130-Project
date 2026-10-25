from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.views import exception_handler
from catalog.models import Listing
from catalog.services import create_listing_draft
from security.permissions import grant_seller


class ListingCreationLimitTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user(email="limited@example.com", email_verified=True)
        grant_seller(self.seller)

    def test_hundredth_succeeds_and_next_returns_429_without_creating_listing(self):
        Listing.objects.bulk_create([Listing(seller=self.seller) for _ in range(99)])
        draft = create_listing_draft(self.seller)
        self.assertEqual(draft.state, Listing.State.DRAFT)
        self.assertEqual(draft.seller, self.seller)
        with self.assertRaises(Throttled) as caught:
            create_listing_draft(self.seller)
        response = exception_handler(caught.exception, {})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(caught.exception.wait, 0)
        self.assertEqual(Listing.objects.filter(seller=self.seller).count(), 100)

    def test_all_states_count_and_limit_is_per_seller(self):
        Listing.objects.bulk_create([
            Listing(seller=self.seller, state=Listing.State.REMOVED) for _ in range(100)
        ])
        with self.assertRaises(Throttled):
            create_listing_draft(self.seller)
        other = get_user_model().objects.create_user(email="unlimited@example.com", email_verified=True)
        grant_seller(other)
        self.assertEqual(create_listing_draft(other).seller, other)

    def test_hour_boundary_releases_capacity(self):
        now = timezone.now()
        Listing.objects.bulk_create([Listing(seller=self.seller) for _ in range(100)])
        oldest = Listing.objects.filter(seller=self.seller).first()
        Listing.objects.filter(pk=oldest.pk).update(created_at=now - timedelta(hours=1))
        with patch("catalog.services.timezone.now", return_value=now):
            create_listing_draft(self.seller)
        self.assertEqual(Listing.objects.filter(seller=self.seller).count(), 101)

    def test_permission_is_rechecked_from_database(self):
        get_user_model().objects.filter(pk=self.seller.pk).update(email_verified=False)
        with self.assertRaises(PermissionDenied):
            create_listing_draft(self.seller)
        self.assertFalse(self.seller.listings.exists())

    def test_anonymous_creation_is_denied(self):
        with self.assertRaises(PermissionDenied):
            create_listing_draft(AnonymousUser())
