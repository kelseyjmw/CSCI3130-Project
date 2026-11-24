from datetime import timedelta

from django.utils import timezone

from catalog.models import AuctionNotification, AuctionOrder, Bid, BidIneligibility, Listing
from catalog.services import process_listing_states, refresh_listing_state
from tests.catalog.auction_helpers import AuctionTestCase


class AuctionCompletionTests(AuctionTestCase):
    def test_highest_bid_creates_one_pending_order_and_private_persistent_notifications(self):
        self.bid('25')
        self.bid('30', self.second_buyer)
        completed = self.finish()
        order = AuctionOrder.objects.get()
        self.assertEqual((completed.state, completed.quantity), ('sold_out', 0))
        self.assertEqual(order.buyer, self.second_buyer)
        self.assertEqual(order.seller, self.seller)
        self.assertEqual((str(order.amount), order.currency, order.quantity, order.payment_status), ('30.00', 'CAD', 1, 'Pending'))
        self.assertEqual(order.winning_bid.amount, order.amount)
        for _ in range(2):
            refresh_listing_state(self.listing.pk)
            process_listing_states()
        self.assertEqual(AuctionOrder.objects.count(), 1)
        self.assertEqual(AuctionNotification.objects.count(), 2)
        for user, expected in ((self.second_buyer, 1), (self.seller, 1), (self.buyer, 0)):
            self.client.force_authenticate(user)
            response = self.client.get('/api/catalog/notifications/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data), expected)
            if expected:
                self.assertEqual(response.data[0]['order_id'], order.pk)
                self.assertEqual(response.data[0]['payment_status'], 'Pending')
        detail = self.client.get(self.detail).data
        self.assertEqual(detail['auction_info']['winning_amount'], '30.00')
        self.assertEqual(detail['display_price'], '30.00')
        self.assertEqual(self.client.get('/api/catalog/listings/').data['count'], 0)
        self.assertEqual(self.client.patch('/api/catalog/notifications/', {}, format='json').status_code, 405)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/catalog/notifications/').status_code, 403)

    def test_no_bid_or_no_eligible_buyer_ends_without_order(self):
        self.assertEqual(self.finish().state, 'ended')
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).quantity, 1)
        self.assertEqual(AuctionOrder.objects.count(), 0)
        self.assertEqual(AuctionNotification.objects.get().recipient, self.seller)

    def test_suspended_leader_bids_stay_immutable_and_ineligible_after_reactivation(self):
        self.bid('25')
        self.bid('30', self.second_buyer)
        before = list(Bid.objects.values_list('amount', 'currency', 'buyer_id', 'created_at'))
        self.suspend(self.second_buyer)
        self.assertEqual(BidIneligibility.objects.count(), 1)
        self.second_buyer.account_state = 'Active'
        self.second_buyer.save(update_fields=['account_state'])
        self.assertEqual(self.client.get(self.detail).data['display_price'], '30.00')
        self.finish()
        order = AuctionOrder.objects.get()
        self.assertEqual(order.buyer, self.buyer)
        self.assertEqual(str(order.amount), '25.00')
        self.assertEqual(self.client.get(self.detail).data['display_price'], '25.00')
        self.assertEqual(before, list(Bid.objects.values_list('amount', 'currency', 'buyer_id', 'created_at')))

    def test_all_buyers_ineligible_produces_no_sale_even_after_reactivation(self):
        self.bid('25')
        self.suspend(self.buyer)
        self.assertEqual(self.finish().state, 'ended')
        self.buyer.account_state = 'Active'
        self.buyer.save(update_fields=['account_state'])
        refresh_listing_state(self.listing.pk)
        self.assertEqual(AuctionOrder.objects.count(), 0)
        self.assertEqual(Bid.objects.count(), 1)

    def test_reactivated_buyer_can_place_a_new_bid_before_the_deadline(self):
        self.bid('25')
        self.suspend(self.buyer)
        self.buyer.account_state = 'Active'
        self.buyer.save(update_fields=['account_state'])
        self.assertEqual(self.bid('27').status_code, 201)
        self.finish()
        self.assertEqual(str(AuctionOrder.objects.get().amount), '27.00')
        self.assertEqual(BidIneligibility.objects.count(), 1)

    def test_bidder_suspended_after_deadline_but_before_completion_cannot_receive_award(self):
        self.bid('25')
        self.bid('30', self.second_buyer)
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.suspend(self.second_buyer)
        refresh_listing_state(self.listing.pk)
        self.assertEqual(AuctionOrder.objects.get().buyer, self.buyer)

    def test_seller_suspension_cancels_unfinished_auction_and_reactivation_does_not_reopen_it(self):
        self.bid('25')
        self.suspend(self.seller)
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).state, 'ended')
        self.seller.account_state = 'Active'
        self.seller.save(update_fields=['account_state'])
        self.assertEqual(self.bid('30').status_code, 400)
        self.finish()
        self.assertEqual(AuctionOrder.objects.count(), 0)
        self.assertEqual(Bid.objects.count(), 1)

    def test_late_removal_before_processing_prevents_sale_and_preserves_bids(self):
        self.bid('25')
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.client.force_authenticate(self.moderator)
        response = self.client.post(self.detail + 'remove/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['state'], 'removed')
        refresh_listing_state(self.listing.pk)
        self.assertEqual(AuctionOrder.objects.count(), 0)
        self.assertEqual(Bid.objects.count(), 1)
        self.assertEqual(self.client.get(self.bids_url).status_code, 200)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get(self.detail).status_code, 403)
        self.assertEqual(self.bid('30').status_code, 400)

    def test_late_suspension_before_processing_prevents_sale(self):
        self.bid('25')
        Listing.objects.filter(pk=self.listing.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.suspend(self.seller)
        process_listing_states()
        self.assertEqual(AuctionOrder.objects.count(), 0)
        self.assertEqual(Listing.objects.get(pk=self.listing.pk).state, 'ended')

    def test_removal_and_suspension_after_completion_preserve_the_existing_order(self):
        self.bid('25')
        self.finish()
        order_id = AuctionOrder.objects.get().pk
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.post(self.detail + 'remove/', {}, format='json').status_code, 200)
        self.suspend(self.seller)
        self.suspend(self.buyer)
        self.seller.account_state = 'Active'
        self.seller.save(update_fields=['account_state'])
        refresh_listing_state(self.listing.pk)
        self.assertEqual(AuctionOrder.objects.get().pk, order_id)
        self.assertEqual(AuctionNotification.objects.count(), 2)
