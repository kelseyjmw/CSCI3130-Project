from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Auction, Category, Listing
from catalog.services import decrease_listing_stock, refresh_listing_state, set_listing_stock
from tests.catalog.helpers import CatalogAPITestCase


class AuctionListingTests(CatalogAPITestCase):
    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name="Auction laptops")
        self.fields = {
            "listing_type": "auction", "title": "Working auction laptop",
            "description": "A fully working laptop sold by auction.", "category": self.category.pk,
            "condition": "used_good", "country": "CA", "postal_code": "B3H 1A1",
            "price": "20.00", "currency": "CAD", "minimum_bid_increment": "2.00",
            "ends_at": (timezone.now() + timedelta(hours=1)).isoformat(),
        }
        created = self.client.post('/api/catalog/listings/', self.fields, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.listing = Listing.objects.get(pk=created.data['id'])
        self.detail = f'/api/catalog/listings/{self.listing.pk}/'
        self.images = self.detail + 'images/'
        self.assertEqual(self.upload().status_code, 201)

    def action(self, name):
        return self.client.post(self.detail + name + '/', {}, format='json')

    def test_fixed_price_default_and_auction_publication_share_existing_fields(self):
        fixed = self.client.post('/api/catalog/listings/', {}, format='json')
        self.assertEqual(fixed.data['listing_type'], 'fixed_price')
        self.assertIsNone(fixed.data['minimum_bid_increment'])
        response = self.action('publish')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['quantity'], 1)
        self.assertEqual(response.data['price'], '20.00')
        self.assertEqual(response.data['display_price'], '20.00')
        self.assertEqual(response.data['minimum_bid_increment'], '2.00')
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.get_display_price(), Decimal('20.00'))
        self.assertEqual(self.listing.ends_at.utcoffset(), timedelta(0))
        self.assertGreater(self.listing.ends_at, self.listing.published_at)

    def test_publication_requires_the_existing_verified_active_seller_permissions(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.action('publish').status_code, 403)
        self.client.force_authenticate(self.seller)
        for field, value, original in (
            ('email_verified', False, True), ('account_state', 'Suspended', 'Active'),
        ):
            setattr(self.seller, field, value)
            self.seller.save(update_fields=[field])
            self.assertEqual(self.action('publish').status_code, 403)
            setattr(self.seller, field, original)
            self.seller.save(update_fields=[field])
        self.assertEqual(self.action('publish').status_code, 200)

    def test_invalid_auction_values_are_rejected_without_creating_records(self):
        count = Listing.objects.count()
        for field, value in (
            ('listing_type', 'invalid'), ('quantity', 0), ('quantity', 2),
            ('price', '0'), ('price', '1.001'), ('price', 'NaN'),
            ('minimum_bid_increment', '0'), ('minimum_bid_increment', '-1'),
            ('minimum_bid_increment', '2.001'), ('minimum_bid_increment', 'Infinity'),
            ('ends_at', (timezone.now() - timedelta(seconds=1)).isoformat()),
        ):
            with self.subTest(field=field, value=value):
                response = self.client.post('/api/catalog/listings/', {**self.fields, field: value}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertEqual(Listing.objects.count(), count)

    def test_incomplete_auction_draft_requires_increment_end_and_release_three_fields_to_publish(self):
        draft = self.client.post('/api/catalog/listings/', {'listing_type': 'auction'}, format='json')
        self.assertEqual(draft.status_code, 201)
        response = self.client.post(f'/api/catalog/listings/{draft.data["id"]}/publish/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('ends_at', response.data)
        self.assertIn('minimum_bid_increment', response.data)
        Listing.objects.filter(pk=self.listing.pk).update(category=None)
        self.assertIn('category', self.action('publish').data)
        Listing.objects.filter(pk=self.listing.pk).update(category=self.category)
        self.listing.images.all().delete()
        self.assertIn('images', self.action('publish').data)

    def test_sale_type_can_change_in_drafts_but_never_after_publication(self):
        response = self.client.patch(self.detail, {'listing_type': 'fixed_price'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(Auction.objects.filter(listing=self.listing).exists())
        response = self.client.patch(self.detail, {'listing_type': 'auction', 'minimum_bid_increment': '3'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['minimum_bid_increment'], '3.00')
        self.assertEqual(self.action('publish').status_code, 200)
        for state in ('active', 'paused', 'ended', 'sold_out'):
            Listing.objects.filter(pk=self.listing.pk).update(state=state)
            response = self.client.patch(self.detail, {'listing_type': 'fixed_price'}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('listing_type', response.data)

    def test_pause_resume_and_early_end_keep_dates_and_one_unsold_item(self):
        self.action('publish')
        self.listing.refresh_from_db()
        published_at, ends_at = self.listing.published_at, self.listing.ends_at
        self.assertEqual(self.action('pause').status_code, 200)
        self.assertEqual(self.action('resume').status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual((self.listing.published_at, self.listing.ends_at), (published_at, ends_at))
        self.assertEqual(self.action('end').data['state'], 'ended')
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).quantity, 1)

    def test_end_time_edits_must_be_future_and_expired_auctions_cannot_resume(self):
        self.action('publish')
        response = self.client.patch(self.detail, {'ends_at': (timezone.now() - timedelta(seconds=1)).isoformat()}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('ends_at', response.data)
        self.action('pause')
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.action('resume').status_code, 400)
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).state, 'ended')

    def test_auction_stock_cannot_be_increased_or_used_by_fixed_price_purchase(self):
        self.action('publish')
        response = self.client.patch(self.detail, {'quantity': 2}, format='json')
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(ValidationError):
            set_listing_stock(self.listing.pk, 0)
        with self.assertRaises(ValidationError):
            decrease_listing_stock(self.listing.pk, 1)
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).quantity, 1)

    def test_auction_lock_overrides_stock_and_moderator_edit_permissions(self):
        self.action('publish')
        # The future accepted-bid workflow will set the shared lock timestamp.
        Listing.objects.filter(pk=self.listing.pk).update(details_locked_at=timezone.now())
        for actor in (self.seller, self.moderator):
            self.client.force_authenticate(actor)
            self.assertIn(self.client.patch(self.detail, {'title': 'A changed title'}, format='json').status_code, (400, 403))
            self.assertIn(self.upload().status_code, (400, 403))
            for action in ('pause', 'end'):
                self.assertIn(self.action(action).status_code, (400, 403))
        with self.assertRaises(ValidationError):
            set_listing_stock(self.listing.pk, 2)
        self.assertEqual(self.action('remove').data['state'], 'removed')
        self.assertTrue(Auction.objects.filter(listing=self.listing).exists())

    def test_search_filters_visibility_and_expiry_use_the_initial_auction_price(self):
        self.action('publish')
        self.client.force_authenticate(None)
        response = self.client.get('/api/catalog/listings/', {'min_price': '20', 'max_price': '20', 'ordering': 'price'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['listing_type'], 'auction')
        self.assertEqual(response.data['results'][0]['price'], '20.00')
        self.assertEqual(self.client.get('/api/catalog/listings/', {'min_price': '20.01'}).data['count'], 0)
        type(self.seller).objects.filter(pk=self.seller.pk).update(account_state='Suspended')
        self.assertEqual(self.client.get('/api/catalog/listings/').data['count'], 0)
        type(self.seller).objects.filter(pk=self.seller.pk).update(account_state='Active')
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(refresh_listing_state(self.listing.pk).state, 'ended')
        self.assertEqual(self.client.get('/api/catalog/listings/').data['count'], 0)
