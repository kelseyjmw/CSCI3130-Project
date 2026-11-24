from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Wallet
from catalog.models import Listing
from commerce.cart import add_to_cart, cart_display, cart_warnings, checkout_quote, remove_from_cart, set_display_currency, set_quantity
from commerce.models import Cart
from security.permissions import grant_seller


class CartTests(TestCase):
    def setUp(self):
        user = get_user_model()
        self.seller = user.objects.create_user('seller@example.com', email_verified=True)
        self.buyer = user.objects.create_user('buyer@example.com', email_verified=True)

    def test_adding_the_same_fixed_price_listing_combines_quantities(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=5, price='20.00', currency='CAD',
        )

        add_to_cart(self.buyer, listing, 1)
        cart = add_to_cart(self.buyer, listing, 1)

        self.assertEqual(cart.lines.count(), 1)
        line = cart.lines.get()
        self.assertEqual((line.listing, line.quantity), (listing, 2))

    def test_auction_listing_is_rejected(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='auction', state='active', quantity=1, price='20.00', currency='CAD',
        )

        with self.assertRaises(ValidationError) as caught:
            add_to_cart(self.buyer, listing, 1)

        self.assertIn('Auction', str(caught.exception))
        self.assertFalse(Cart.objects.filter(user=self.buyer).exists())

    def test_quantity_above_available_stock_is_rejected(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=2, price='20.00', currency='CAD',
        )

        with self.assertRaises(ValidationError) as caught:
            add_to_cart(self.buyer, listing, 3)
        self.assertIn('stock', str(caught.exception))
        self.assertFalse(Cart.objects.filter(user=self.buyer).exists())

        add_to_cart(self.buyer, listing, 2)
        with self.assertRaises(ValidationError):
            add_to_cart(self.buyer, listing, 1)
        self.assertEqual(Cart.objects.get(user=self.buyer).lines.get().quantity, 2)

    def test_buyer_can_change_a_quantity_or_remove_the_line(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=5, price='20.00', currency='CAD',
        )
        add_to_cart(self.buyer, listing, 2)

        cart = set_quantity(self.buyer, listing, 1)
        self.assertEqual(cart.lines.get().quantity, 1)
        with self.assertRaises(ValidationError):
            set_quantity(self.buyer, listing, 0)
        with self.assertRaises(ValidationError):
            set_quantity(self.buyer, listing, 6)
        self.assertEqual(cart.lines.get().quantity, 1)

        remove_from_cart(self.buyer, listing)
        self.assertEqual(cart.lines.count(), 0)

    def test_unavailable_item_stays_in_the_cart_and_is_reported(self):
        grant_seller(self.seller)
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=2, price='20.00', currency='CAD',
        )
        add_to_cart(self.buyer, listing, 1)
        Listing.objects.filter(pk=listing.pk).update(state='paused')

        self.assertEqual(cart_warnings(self.buyer), [f'Listing {listing.pk} is no longer available.'])
        self.assertEqual(Cart.objects.get(user=self.buyer).lines.count(), 1)

    def test_display_currency_changes_shown_prices_only(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=2, price='10.00', currency='USD',
        )
        add_to_cart(self.buyer, listing, 1)
        set_display_currency(self.buyer, 'CAD')

        shown = cart_display(self.buyer)
        self.assertEqual((shown['currency'], shown['lines'][0]['unit_price'], shown['total']), ('CAD', Decimal('14.00'), Decimal('14.00')))
        listing.refresh_from_db()
        self.assertEqual((listing.price, listing.currency), (Decimal('10.00'), 'USD'))

        set_display_currency(self.buyer, 'USD')
        shown = cart_display(self.buyer)
        self.assertEqual((shown['currency'], shown['lines'][0]['unit_price']), ('USD', Decimal('10.00')))
        with self.assertRaises(ValidationError):
            set_display_currency(self.buyer, 'EUR')
        self.assertEqual(Cart.objects.get(user=self.buyer).display_currency, 'USD')

    def test_guest_cart_stays_on_the_session_and_is_not_merged(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=5, price='20.00', currency='CAD',
        )
        add_to_cart(None, listing, 1, session_key='guest-session')
        add_to_cart(None, listing, 1, session_key='guest-session')
        add_to_cart(self.buyer, listing, 1)

        guest = Cart.objects.get(session_key='guest-session')
        member = Cart.objects.get(user=self.buyer)
        self.assertIsNone(guest.user)
        self.assertEqual(guest.lines.get().quantity, 2)
        self.assertEqual(member.lines.get().quantity, 1)
        self.assertEqual(Cart.objects.filter(session_key='guest-session').count(), 1)

    def test_checkout_quotes_the_whole_cart_without_charging_the_wallet(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='10.00', currency='USD',
        )
        add_to_cart(self.buyer, listing, 1)
        set_display_currency(self.buyer, 'USD')
        with self.assertRaises(ValidationError) as caught:
            checkout_quote(self.buyer)
        self.assertIn('wallet', str(caught.exception))

        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('30.00'))
        Wallet.objects.create(user=self.seller, currency='USD', balance=Decimal('0.00'))
        quote = checkout_quote(self.buyer)

        self.assertEqual((quote['buyer_total'], quote['buyer_currency']), (Decimal('20.40'), 'CAD'))
        self.assertEqual((quote['display']['total'], quote['display']['currency']), (Decimal('14.57'), 'USD'))
        self.buyer.wallet.refresh_from_db()
        self.seller.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('30.00'))
        self.assertEqual(self.seller.wallet.balance, Decimal('0.00'))
        self.assertEqual(Cart.objects.get(user=self.buyer).lines.get().quantity, 1)
