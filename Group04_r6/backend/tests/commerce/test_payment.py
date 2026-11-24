from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Wallet, WalletTransaction
from catalog.auctions import complete_auction
from catalog.models import Auction, AuctionOrder, Bid, Listing
from commerce.cart import add_to_cart, set_display_currency
from commerce.checkout import save_delivery_address, start_checkout
from commerce.models import Cart, Order
from commerce.payment import (
    pay_auction_order,
    pay_order,
    quote_auction_order,
    view_auction_order,
)
from security.permissions import assign_buyer, grant_seller

ADDRESS = {
    'full_name': 'Jane Doe',
    'line1': '123 Barrington St',
    'city': 'Halifax',
    'region': 'NS',
    'postal_code': 'B3J 2A8',
    'country': 'Canada',
}


def make_member(email, **kwargs):
    user = get_user_model().objects.create_user(email, email_verified=True, **kwargs)
    assign_buyer(user)
    return user


class PaymentAndSettlementTests(TestCase):
    def setUp(self):
        self.seller_cad = make_member('seller_cad@example.com')
        self.seller_usd = make_member('seller_usd@example.com')
        self.buyer = make_member('buyer@example.com')
        self.other_buyer = make_member('buyer2@example.com')
        grant_seller(self.seller_cad)
        grant_seller(self.seller_usd)

        Wallet.objects.create(user=self.seller_cad, currency='CAD', balance=Decimal('0.00'))
        Wallet.objects.create(user=self.seller_usd, currency='USD', balance=Decimal('0.00'))

    def test_guest_wallet_constraints_and_session_warning(self):
        client = APIClient()
        res = client.post('/api/accounts/wallet/create/', {'currency': 'CAD'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data['is_guest'])
        self.assertIn('closing your browser session will lose access', res.data['warning'].lower())

        topup = client.post(
            '/api/accounts/wallet/topup/',
            {'amount': '50.00', 'card_number': '1234567812345678', 'cvv': '123', 'expiry': '12/2028'},
            format='json',
        )
        self.assertEqual(topup.status_code, 200)
        self.assertEqual(Decimal(topup.data['balance']), Decimal('50.00'))

        # DB XOR check constraint prevents a wallet with neither user nor session_key
        with self.assertRaises(IntegrityError):
            Wallet.objects.create(currency='CAD', balance=Decimal('0.00'))

    def test_successful_order_payment_transfers_funds_updates_stock_and_clears_cart(self):
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        listing_usd = Listing.objects.create(
            seller=self.seller_usd, listing_type='fixed_price', state='active',
            quantity=1, price='10.00', currency='USD',
        )
        listing_cad = Listing.objects.create(
            seller=self.seller_cad, listing_type='fixed_price', state='active',
            quantity=3, price='20.00', currency='CAD',
        )

        add_to_cart(self.buyer, listing_usd, 1)
        add_to_cart(self.buyer, listing_cad, 2)
        set_display_currency(self.buyer, 'CAD')
        order = start_checkout(self.buyer)
        save_delivery_address(self.buyer, ADDRESS)

        # Seller USD share: 14.00 + 1.40 tax + 5.00 delivery = 20.40 CAD -> 14.57 USD
        # Seller CAD share: 40.00 + 4.00 tax + 5.00 delivery = 49.00 CAD -> 49.00 CAD
        # Total buyer charge = 69.40 CAD
        result = pay_order(order.pk, self.buyer)
        self.assertEqual(result['payment_status'], 'Paid')
        self.assertFalse(result['already_paid'])

        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'Paid')

        self.buyer.wallet.refresh_from_db()
        self.seller_usd.wallet.refresh_from_db()
        self.seller_cad.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('30.60'))
        self.assertEqual(self.seller_usd.wallet.balance, Decimal('14.57'))
        self.assertEqual(self.seller_cad.wallet.balance, Decimal('49.00'))

        # Verify WalletTransaction records identify the order
        buyer_tx = WalletTransaction.objects.get(wallet=self.buyer.wallet)
        self.assertEqual(buyer_tx.transaction_type, WalletTransaction.TransactionType.PAYMENT)
        self.assertEqual(buyer_tx.amount, Decimal('69.40'))
        self.assertEqual(buyer_tx.reference, f'Order #{order.pk}')

        # Stock reduced; listing_usd reached 0 and transitioned to sold_out
        listing_usd.refresh_from_db()
        listing_cad.refresh_from_db()
        self.assertEqual(listing_usd.quantity, 0)
        self.assertEqual(listing_usd.state, Listing.State.SOLD_OUT)
        self.assertEqual(listing_cad.quantity, 1)
        self.assertEqual(listing_cad.state, Listing.State.ACTIVE)

        # Cart is emptied and unlocked
        cart = Cart.objects.get(user=self.buyer)
        self.assertEqual(cart.lines.count(), 0)
        self.assertFalse(cart.checking_out)

    def test_duplicate_payment_on_paid_order_is_idempotent(self):
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        listing = Listing.objects.create(
            seller=self.seller_cad, listing_type='fixed_price', state='active',
            quantity=2, price='20.00', currency='CAD',
        )
        add_to_cart(self.buyer, listing, 1)
        order = start_checkout(self.buyer)
        save_delivery_address(self.buyer, ADDRESS)

        first = pay_order(order.pk, self.buyer)
        self.assertFalse(first['already_paid'])

        second = pay_order(order.pk, self.buyer)
        self.assertTrue(second['already_paid'])

        self.buyer.wallet.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('73.00'))
        self.assertEqual(listing.quantity, 1)

    def test_insufficient_balance_leaves_order_pending_and_stock_unchanged(self):
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('10.00'))
        listing = Listing.objects.create(
            seller=self.seller_cad, listing_type='fixed_price', state='active',
            quantity=2, price='20.00', currency='CAD',
        )
        add_to_cart(self.buyer, listing, 1)
        order = start_checkout(self.buyer)
        save_delivery_address(self.buyer, ADDRESS)

        with self.assertRaises(ValidationError) as caught:
            pay_order(order.pk, self.buyer)
        self.assertIn('Insufficient', str(caught.exception))

        order.refresh_from_db()
        listing.refresh_from_db()
        self.buyer.wallet.refresh_from_db()
        self.assertEqual(order.payment_status, 'Pending')
        self.assertEqual(listing.quantity, 2)
        self.assertEqual(self.buyer.wallet.balance, Decimal('10.00'))
        self.assertEqual(Cart.objects.get(user=self.buyer).lines.count(), 1)

    def test_last_item_purchase_blocks_second_buyer_without_negative_stock(self):
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        Wallet.objects.create(user=self.other_buyer, currency='CAD', balance=Decimal('100.00'))
        listing = Listing.objects.create(
            seller=self.seller_cad, listing_type='fixed_price', state='active',
            quantity=1, price='20.00', currency='CAD',
        )

        add_to_cart(self.buyer, listing, 1)
        add_to_cart(self.other_buyer, listing, 1)

        order1 = start_checkout(self.buyer)
        save_delivery_address(self.buyer, ADDRESS)

        order2 = start_checkout(self.other_buyer)
        save_delivery_address(self.other_buyer, ADDRESS)

        pay_order(order1.pk, self.buyer)

        with self.assertRaises(ValidationError):
            pay_order(order2.pk, self.other_buyer)

        listing.refresh_from_db()
        self.assertEqual(listing.quantity, 0)
        self.assertEqual(listing.state, Listing.State.SOLD_OUT)
        self.other_buyer.wallet.refresh_from_db()
        self.assertEqual(self.other_buyer.wallet.balance, Decimal('100.00'))

    def test_guest_checkout_and_payment_using_guest_session_wallet(self):
        Wallet.objects.create(session_key='guest-sess-1', currency='CAD', balance=Decimal('50.00'))
        listing = Listing.objects.create(
            seller=self.seller_cad, listing_type='fixed_price', state='active',
            quantity=2, price='20.00', currency='CAD',
        )
        add_to_cart(None, listing, 1, session_key='guest-sess-1')
        order = start_checkout(None, session_key='guest-sess-1', guest_email='guest@example.com')
        save_delivery_address(None, ADDRESS, session_key='guest-sess-1')

        res = pay_order(order.pk, None, session_key='guest-sess-1')
        self.assertEqual(res['payment_status'], 'Paid')

        guest_wallet = Wallet.objects.get(session_key='guest-sess-1')
        self.assertEqual(guest_wallet.balance, Decimal('23.00'))
        listing.refresh_from_db()
        self.assertEqual(listing.quantity, 1)

    def test_restricted_signed_in_account_cannot_pay(self):
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        listing = Listing.objects.create(
            seller=self.seller_cad, listing_type='fixed_price', state='active',
            quantity=2, price='20.00', currency='CAD',
        )
        add_to_cart(self.buyer, listing, 1)
        order = start_checkout(self.buyer)
        save_delivery_address(self.buyer, ADDRESS)

        # Suspend buyer after checkout started; payment must be refused
        self.buyer.account_state = 'Suspended'
        self.buyer.save(update_fields=['account_state'])

        with self.assertRaises(ValidationError):
            pay_order(order.pk, self.buyer)

    def test_auction_win_payment_settles_without_clearing_cart_or_reducing_stock_twice(self):
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('200.00'))

        # Buyer already has an unrelated item in their shopping cart
        cart_listing = Listing.objects.create(
            seller=self.seller_cad, listing_type='fixed_price', state='active',
            quantity=5, price='15.00', currency='CAD',
        )
        add_to_cart(self.buyer, cart_listing, 2)

        # Create and complete a Release 5 auction (which sets listing.quantity=0 & state='sold_out')
        now = timezone.now()
        auction_listing = Listing.objects.create(
            seller=self.seller_usd, listing_type='auction', state='active',
            quantity=1, price='50.00', currency='USD', ends_at=now - timedelta(minutes=1),
        )
        auction = Auction.objects.create(listing=auction_listing, minimum_bid_increment=Decimal('5.00'))
        Bid.objects.create(
            auction=auction, buyer=self.buyer, amount=Decimal('50.00'),
            currency='USD', created_at=now - timedelta(minutes=5),
        )
        with patch('django.utils.timezone.now', return_value=now):
            complete_auction(auction_listing, now)

        auction_listing.refresh_from_db()
        self.assertEqual(auction_listing.state, Listing.State.SOLD_OUT)
        self.assertEqual(auction_listing.quantity, 0)

        auction_order = AuctionOrder.objects.get(auction=auction)
        self.assertEqual(auction_order.payment_status, 'Pending')

        # Seller cannot see delivery address before payment
        pre_seller_view = view_auction_order(auction_order.pk, self.seller_usd)
        self.assertIsNone(pre_seller_view['address'])

        # Quote: 50.00 USD = 70.00 CAD + 7.00 tax + 5.00 delivery = 82.00 CAD -> 58.57 USD seller credit
        quote = quote_auction_order(auction_order.pk, self.buyer)
        self.assertEqual(quote['buyer_total'], Decimal('82.00'))
        self.assertEqual(quote['seller_credit'], Decimal('58.57'))

        # Pay auction order via API endpoint
        client = APIClient()
        client.force_authenticate(user=self.buyer)
        pay_res = client.post(
            f'/api/commerce/auction-orders/{auction_order.pk}/pay/',
            {'address': ADDRESS},
            format='json',
        )
        self.assertEqual(pay_res.status_code, 200)
        self.assertEqual(pay_res.data['payment_status'], 'Paid')
        self.assertFalse(pay_res.data['already_paid'])

        # Idempotent second payment call
        paid_again = pay_auction_order(auction_order.pk, self.buyer, ADDRESS)
        self.assertTrue(paid_again['already_paid'])

        # Verify balances, stock untouched (still 0, no error), and cart untouched (still 2 items)
        self.buyer.wallet.refresh_from_db()
        self.seller_usd.wallet.refresh_from_db()
        auction_listing.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('118.00'))
        self.assertEqual(self.seller_usd.wallet.balance, Decimal('58.57'))
        self.assertEqual(auction_listing.quantity, 0)
        self.assertEqual(Cart.objects.get(user=self.buyer).lines.get().quantity, 2)

        # No duplicate cart Order created
        self.assertEqual(Order.objects.count(), 0)

        # Seller can now view delivery address after Paid
        post_seller_view = view_auction_order(auction_order.pk, self.seller_usd)
        self.assertEqual(post_seller_view['address']['postal_code'], 'B3J 2A8')