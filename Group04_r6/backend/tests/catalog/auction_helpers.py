from datetime import timedelta

from django.utils import timezone
from catalog.models import Auction, Category, Listing
from catalog.services import refresh_listing_state
from security.permissions import assign_buyer
from tests.catalog.helpers import CatalogAPITestCase


class AuctionTestCase(CatalogAPITestCase):
    def setUp(self):
        super().setUp()
        category = Category.objects.create(name='Bid test category')
        Listing.objects.filter(pk=self.listing.pk).update(
            listing_type='auction', state='active', quantity=1, price='20.00', currency='CAD',
            title='Working auction laptop', description='A fully working laptop with a charger.',
            category=category, condition='used_good', country='CA', postal_code='B3H 1A1',
            published_at=timezone.now() - timedelta(minutes=1), ends_at=timezone.now() + timedelta(hours=1),
        )
        self.auction = Auction.objects.create(listing=self.listing, minimum_bid_increment='2.00')
        self.listing.refresh_from_db()
        self.buyer = self.other
        self.second_buyer = type(self.buyer).objects.create_user('second-bidder@example.com', email_verified=True)
        assign_buyer(self.second_buyer)
        self.client.force_authenticate(self.buyer)
        self.bids_url = self.detail + 'bids/'

    def bid(self, amount, buyer=None, **extra):
        self.client.force_authenticate(buyer or self.buyer)
        return self.client.post(self.bids_url, {'amount': amount, 'currency': 'CAD', **extra}, format='json')

    def finish(self):
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        return refresh_listing_state(self.listing.pk)

    def suspend(self, user):
        user.account_state = 'Suspended'
        user.save(update_fields=['account_state'])
