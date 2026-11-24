from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError as ModelValidationError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Bid, Listing
from catalog.services import decrease_listing_stock, set_listing_stock
from tests.catalog.auction_helpers import AuctionTestCase
from tests.catalog.helpers import image_upload


class BiddingTests(AuctionTestCase):
    def test_first_bid_increment_leader_raise_and_current_price_in_search(self):
        self.assertEqual(self.bid('20').status_code, 201)
        rejected = self.bid('21', self.second_buyer)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(str(rejected.data['minimum_bid']), '22.00')
        self.assertEqual(self.bid('22').status_code, 201)  # The leader can raise their own bid.
        self.assertEqual(self.bid('30', self.second_buyer).status_code, 201)
        detail = self.client.get(self.detail).data
        self.assertEqual(detail['display_price'], '30.00')
        self.assertEqual(detail['auction_info']['minimum_next_bid'], '32.00')
        self.assertEqual(detail['auction_info']['leader'], Bid.objects.order_by('-amount').first().bidder_label)
        self.assertEqual(detail['quantity'], 1)
        match = self.client.get('/api/catalog/listings/', {'min_price': '30', 'max_price': '30', 'ordering': 'price'}).data
        self.assertEqual(match['count'], 1)
        self.assertEqual(match['results'][0]['price'], '30.00')
        self.assertEqual(self.client.get('/api/catalog/listings/', {'max_price': '29.99'}).data['count'], 0)
        fixed = Listing.objects.create(seller=self.seller, state='active', quantity=1, currency='CAD', price='25.00')
        for ordering, expected in (('price', [fixed.pk, self.listing.pk]), ('-price', [self.listing.pk, fixed.pk])):
            response = self.client.get('/api/catalog/listings/', {'ordering': ordering})
            self.assertEqual([row['id'] for row in response.data['results']], expected)

    def test_invalid_amount_currency_and_extra_fields_never_create_accepted_bids(self):
        for amount in (None, True, 'NaN', 'Infinity', '-1', '0', '20.001', 'not-a-number'):
            with self.subTest(amount=amount):
                self.assertEqual(self.bid(amount).status_code, 400)
        self.assertEqual(self.bid('25', currency='USD').status_code, 400)
        self.assertEqual(self.bid('25', buyer_id=self.seller.pk).status_code, 400)
        self.assertEqual(self.bid('19.99').status_code, 400)
        self.assertEqual(Bid.objects.count(), 0)

    def test_guest_unverified_suspended_inactive_unprivileged_and_seller_cannot_bid(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.bids_url, {'amount': '25'}, format='json').status_code, 403)
        self.assertEqual(self.bid('25', self.seller).status_code, 403)
        for field, value, original in (('email_verified', False, True), ('is_active', False, True), ('account_state', 'Suspended', 'Active')):
            setattr(self.buyer, field, value)
            self.buyer.save(update_fields=[field])
            self.assertEqual(self.bid('25').status_code, 403)
            setattr(self.buyer, field, original)
            self.buyer.save(update_fields=[field])
        unprivileged = type(self.buyer).objects.create_user('no-buy-permission@example.com', email_verified=True)
        self.assertEqual(self.bid('25', unprivileged).status_code, 403)
        self.assertEqual(Bid.objects.count(), 0)

    def test_only_active_auctions_accept_bids_strictly_before_server_deadline(self):
        for state in ('draft', 'paused', 'ended', 'sold_out', 'removed'):
            Listing.objects.filter(pk=self.listing.pk).update(state=state)
            self.assertEqual(self.bid('25').status_code, 400)
        Listing.objects.filter(pk=self.listing.pk).update(state='active')
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=None)
        self.assertEqual(self.client.get('/api/catalog/listings/').data['count'], 0)
        self.assertFalse(self.client.get(self.detail).data['auction_info']['can_bid'])
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=self.listing.ends_at)
        deadline = self.listing.ends_at
        with patch('django.utils.timezone.now', return_value=deadline):
            self.assertEqual(self.bid('25').status_code, 400)
        self.assertEqual(Bid.objects.count(), 0)
        Listing.objects.filter(pk=self.listing.pk).update(listing_type='fixed_price', state='active')
        self.assertEqual(self.bid('25').status_code, 400)

    def test_history_is_ordered_anonymous_and_accepted_records_are_immutable(self):
        self.buyer.display_name = 'Private Full Name'
        self.buyer.save(update_fields=['display_name'])
        self.bid('25')
        self.bid('30', self.second_buyer)
        self.client.force_authenticate(None)
        history = self.client.get(self.bids_url)
        self.assertEqual([row['amount'] for row in history.data], ['25.00', '30.00'])
        self.assertNotIn('Private Full Name', history.content.decode())
        self.assertNotIn(self.buyer.email, history.content.decode())
        self.assertTrue(all(row['bidder'].startswith('Bidder ') and row['created_at'] for row in history.data))
        record = Bid.objects.first()
        self.assertEqual(record.currency, 'CAD')
        self.assertEqual(record.buyer, self.buyer)
        for operation in (lambda: record.save(), lambda: record.delete(),
                          lambda: Bid.objects.filter(pk=record.pk).update(amount=100), lambda: Bid.objects.all().delete()):
            with self.assertRaises(ModelValidationError):
                operation()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.patch(self.bids_url, {'amount': '5'}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(self.bids_url).status_code, 405)
        self.assertEqual(Bid.objects.first().amount, Decimal('25.00'))

    def test_first_bid_locks_fields_images_stock_and_early_actions_even_for_moderators(self):
        self.bid('25')
        for actor in (self.seller, self.moderator):
            self.client.force_authenticate(actor)
            for fields in ({'price': '100'}, {'currency': 'USD'}, {'ends_at': None}, {'quantity': 2}):
                self.assertIn(self.client.patch(self.detail, fields, format='json').status_code, (400, 403))
            self.assertEqual(self.client.post(self.images, {'file': image_upload()}, format='multipart').status_code, 403)
            for action in ('pause', 'end'):
                self.assertEqual(self.client.post(self.detail + action + '/', {}, format='json').status_code, 403)
        for operation in (lambda: set_listing_stock(self.listing.pk, 2), lambda: decrease_listing_stock(self.listing.pk, 1)):
            with self.assertRaises(ValidationError):
                operation()
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).quantity, 1)
