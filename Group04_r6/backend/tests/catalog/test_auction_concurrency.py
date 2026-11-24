from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from catalog.auctions import submit_bid
from catalog.models import Auction, AuctionNotification, AuctionOrder, Bid, Listing
from catalog.services import refresh_listing_state
from security.permissions import assign_buyer, grant_seller
from security.models import Permission, Role


class AuctionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor == 'sqlite' and 'memory' in connection.settings_dict['NAME']:
            self.skipTest('Use a file-backed test database to check SQLite writer serialization.')
        self.seller = User.objects.create_user('auction-owner@example.com', email_verified=True)
        grant_seller(self.seller)
        self.buyers = [User.objects.create_user(f'bidder-{index}@example.com', email_verified=True) for index in range(2)]
        permission, _ = Permission.objects.get_or_create(code='items.buy')
        Role.objects.get_or_create(name='Buyer')[0].permissions.add(permission)
        for buyer in self.buyers:
            assign_buyer(buyer)
        self.listing = Listing.objects.create(
            seller=self.seller, listing_type='auction', state='active', quantity=1,
            title='Concurrency auction', price='20.00', currency='CAD',
            published_at=timezone.now(), ends_at=timezone.now() + timedelta(hours=1),
        )
        Auction.objects.create(listing=self.listing, minimum_bid_increment='2.00')

    def parallel(self, operation):
        barrier = Barrier(2)
        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation(index)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_identical_simultaneous_bids_have_only_one_accepted_record(self):
        def bid(index):
            try:
                submit_bid(self.listing.pk, self.buyers[index], '25.00')
                return 201
            except ValidationError:
                return 400
        self.assertEqual(sorted(self.parallel(bid)), [201, 400])
        self.assertEqual(Bid.objects.count(), 1)

    def test_simultaneous_completion_creates_exactly_one_order_and_notification_pair(self):
        submit_bid(self.listing.pk, self.buyers[0], '25.00')
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.parallel(lambda _: refresh_listing_state(self.listing.pk))
        self.assertEqual(AuctionOrder.objects.count(), 1)
        self.assertEqual(AuctionNotification.objects.count(), 2)
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).state, 'sold_out')
