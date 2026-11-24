from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Wallet
from catalog.models import Listing
from commerce.cart import add_to_cart, remove_from_cart, set_display_currency, set_quantity
from commerce.checkout import (
    confirm_checkout, recheck_before_payment, return_to_cart, review_checkout,
    save_delivery_address, start_checkout, view_guest_order, view_order,
)
from commerce.models import Cart, Order, OrderAddress
from security.models import Role
from security.permissions import assign_buyer, grant_seller


class CheckoutOrderTests(TestCase):
    def setUp(self):
        user = get_user_model()
        self.seller = user.objects.create_user('seller@example.com', email_verified=True)
        self.buyer = user.objects.create_user('buyer@example.com', email_verified=True)
        assign_buyer(self.buyer)

    def test_starting_checkout_twice_returns_one_pending_order(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='10.00', currency='USD',
        )
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('30.00'))
        Wallet.objects.create(user=self.seller, currency='USD')
        add_to_cart(self.buyer, listing, 1)
        set_display_currency(self.buyer, 'USD')

        first = start_checkout(self.buyer)
        second = start_checkout(self.buyer)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(first.payment_status, 'Pending')
        self.assertEqual((first.buyer_total, first.buyer_currency), (Decimal('20.40'), 'CAD'))
        self.assertEqual(
            (first.display_subtotal, first.display_tax, first.display_delivery, first.display_total, first.display_currency),
            (Decimal('10.00'), Decimal('1.00'), Decimal('3.57'), Decimal('14.57'), 'USD'),
        )
        line = first.lines.get()
        self.assertEqual((line.seller, line.quantity, line.unit_price, line.currency), (self.seller, 1, Decimal('10.00'), 'USD'))
        share = first.seller_shares.get()
        self.assertEqual((share.share, share.credit, share.credit_currency), (Decimal('20.40'), Decimal('14.57'), 'USD'))
        self.buyer.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('30.00'))

    def test_cart_stays_locked_until_the_buyer_returns(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=2, price='20.00', currency='CAD',
        )
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        Wallet.objects.create(user=self.seller, currency='CAD')
        add_to_cart(self.buyer, listing, 1)
        order = start_checkout(self.buyer)

        with self.assertRaises(ValidationError):
            add_to_cart(self.buyer, listing, 1)
        with self.assertRaises(ValidationError):
            set_quantity(self.buyer, listing, 2)
        with self.assertRaises(ValidationError):
            remove_from_cart(self.buyer, listing)
        with self.assertRaises(ValidationError):
            set_display_currency(self.buyer, 'USD')
        self.assertEqual(Cart.objects.get(user=self.buyer).lines.get().quantity, 1)

        return_to_cart(self.buyer)
        set_quantity(self.buyer, listing, 2)
        self.assertEqual(Cart.objects.get(user=self.buyer).lines.get().quantity, 2)
        again = start_checkout(self.buyer)
        self.assertEqual(again.pk, order.pk)
        self.assertEqual(again.lines.get().quantity, 1)
        self.assertTrue(Cart.objects.get(user=self.buyer).checking_out)

    def test_delivery_address_is_saved_on_the_order(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        Wallet.objects.create(user=self.seller, currency='CAD')
        add_to_cart(self.buyer, listing, 1)
        order = start_checkout(self.buyer)
        with self.assertRaises(ValidationError):
            save_delivery_address(self.buyer, {
                'full_name': 'Ada Buyer', 'line1': '1 Spring Garden', 'postal_code': 'B3H 1A1', 'country': 'Canada',
            })
        self.assertFalse(OrderAddress.objects.filter(order=order).exists())

        save_delivery_address(self.buyer, {
            'full_name': 'Ada Buyer',
            'line1': '1 Spring Garden',
            'line2': 'Apt 2',
            'city': 'Halifax',
            'region': 'NS',
            'postal_code': 'B3H 1A1',
            'country': 'Canada',
        })
        self.buyer.postal_address = 'Changed later'
        self.buyer.save(update_fields=['postal_address'])
        address = OrderAddress.objects.get(order=order)
        self.assertEqual((address.full_name, address.city, address.line2, address.region), ('Ada Buyer', 'Halifax', 'Apt 2', 'NS'))
        self.assertNotEqual(address.line1, self.buyer.postal_address)

    def test_a_changed_total_is_saved_only_after_confirmation(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=2, price='20.00', currency='CAD',
        )
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        Wallet.objects.create(user=self.seller, currency='CAD')
        add_to_cart(self.buyer, listing, 1)
        order = start_checkout(self.buyer)
        shown = review_checkout(self.buyer)
        self.assertFalse(shown['needs_confirmation'])
        self.assertEqual(
            (shown['display_subtotal'], shown['display_tax'], shown['display_delivery'], shown['display_total'], shown['display_currency']),
            (Decimal('20.00'), Decimal('2.00'), Decimal('5.00'), Decimal('27.00'), 'CAD'),
        )
        self.assertEqual((shown['buyer_total'], shown['buyer_currency']), (Decimal('27.00'), 'CAD'))

        return_to_cart(self.buyer)
        listing.price = Decimal('10.00')
        listing.save(update_fields=['price'])
        set_display_currency(self.buyer, 'USD')
        with self.assertRaises(ValidationError):
            confirm_checkout(self.buyer)
        order.refresh_from_db()
        self.assertEqual((order.buyer_total, order.display_currency), (Decimal('27.00'), 'CAD'))
        self.assertEqual(order.lines.get().unit_price, Decimal('20.00'))

        start_checkout(self.buyer)
        shown = review_checkout(self.buyer)
        self.assertTrue(shown['needs_confirmation'])
        self.assertEqual((shown['buyer_total'], shown['buyer_currency']), (Decimal('16.00'), 'CAD'))
        self.assertEqual((shown['display_total'], shown['display_currency']), (Decimal('11.43'), 'USD'))
        order.refresh_from_db()
        self.assertEqual(order.buyer_total, Decimal('27.00'))

        confirmed = confirm_checkout(self.buyer)
        self.assertEqual(confirmed.pk, order.pk)
        self.assertEqual((confirmed.buyer_total, confirmed.display_currency), (Decimal('16.00'), 'USD'))
        self.assertEqual(confirmed.lines.get().unit_price, Decimal('10.00'))
        self.assertFalse(review_checkout(self.buyer)['needs_confirmation'])
        self.buyer.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('100.00'))

    def test_a_restricted_member_cannot_start_checkout(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        add_to_cart(self.buyer, listing, 1)
        for field, bad, good in (
            ('email_verified', False, True), ('is_active', False, True), ('account_state', 'Suspended', 'Active'),
        ):
            setattr(self.buyer, field, bad)
            self.buyer.save(update_fields=[field])
            with self.assertRaises(ValidationError) as caught:
                start_checkout(self.buyer, session_key='guest-session')
            self.assertIn('permission to buy', str(caught.exception))
            self.assertEqual(Order.objects.count(), 0)
            setattr(self.buyer, field, good)
            self.buyer.save(update_fields=[field])

        Role.objects.get(name='Buyer').users.remove(self.buyer)
        with self.assertRaises(ValidationError) as caught:
            start_checkout(self.buyer, session_key='guest-session')
        self.assertIn('permission to buy', str(caught.exception))
        self.assertEqual(Order.objects.count(), 0)
        self.assertFalse(Cart.objects.get(user=self.buyer).checking_out)

    def test_payment_is_refused_when_the_buyer_or_seller_cannot_trade(self):
        assign_buyer(self.buyer)
        grant_seller(self.seller)
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        Wallet.objects.create(user=self.seller, currency='CAD')
        add_to_cart(self.buyer, listing, 1)
        order = start_checkout(self.buyer)
        self.assertEqual(recheck_before_payment(self.buyer).pk, order.pk)

        for field, bad, good in (
            ('email_verified', False, True), ('is_active', False, True), ('account_state', 'Suspended', 'Active'),
        ):
            setattr(self.buyer, field, bad)
            self.buyer.save(update_fields=[field])
            with self.assertRaises(ValidationError) as caught:
                recheck_before_payment(self.buyer, session_key='guest-session')
            self.assertIn('permission to buy', str(caught.exception))
            setattr(self.buyer, field, good)
            self.buyer.save(update_fields=[field])

        Role.objects.get(name='Buyer').users.remove(self.buyer)
        with self.assertRaises(ValidationError):
            recheck_before_payment(self.buyer)
        assign_buyer(self.buyer)

        self.seller.account_state = 'Suspended'
        self.seller.save(update_fields=['account_state'])
        with self.assertRaises(ValidationError) as caught:
            recheck_before_payment(self.buyer)
        self.assertIn(str(listing.pk), str(caught.exception))
        self.assertIn('cannot sell', str(caught.exception))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'Pending')
        self.buyer.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('100.00'))

        guest_listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        self.seller.account_state = 'Active'
        self.seller.save(update_fields=['account_state'])
        Wallet.objects.create(session_key='guest-session', currency='CAD', balance=Decimal('40.00'))
        add_to_cart(None, guest_listing, 1, session_key='guest-session')
        guest_order = start_checkout(None, session_key='guest-session', guest_email='guest@example.com')
        self.assertEqual(recheck_before_payment(None, session_key='guest-session').pk, guest_order.pk)
        self.assertEqual(guest_order.payment_status, 'Pending')

    def test_payment_recheck_names_a_line_that_cannot_be_bought(self):
        assign_buyer(self.buyer)
        grant_seller(self.buyer)
        own = Listing.objects.create(
            seller=self.buyer, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        add_to_cart(self.buyer, own, 1)
        start_checkout(self.buyer)
        with self.assertRaises(ValidationError) as caught:
            recheck_before_payment(self.buyer)
        self.assertIn(str(own.pk), str(caught.exception))
        self.assertIn('own listing', str(caught.exception))

        grant_seller(self.seller)
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=2, price='20.00', currency='CAD',
        )
        Wallet.objects.create(user=self.seller, currency='CAD')
        return_to_cart(self.buyer)
        remove_from_cart(self.buyer, own)
        add_to_cart(self.buyer, listing, 2)
        order = start_checkout(self.buyer)
        confirm_checkout(self.buyer)
        self.assertEqual(recheck_before_payment(self.buyer).payment_status, 'Pending')

        Listing.objects.filter(pk=listing.pk).update(quantity=1)
        with self.assertRaises(ValidationError) as caught:
            recheck_before_payment(self.buyer)
        self.assertIn('stock', str(caught.exception))

        Listing.objects.filter(pk=listing.pk).update(quantity=2, state='paused')
        with self.assertRaises(ValidationError) as caught:
            recheck_before_payment(self.buyer)
        self.assertIn('no longer available', str(caught.exception))

        Listing.objects.filter(pk=listing.pk).update(state='active', price=Decimal('10.00'))
        with self.assertRaises(ValidationError) as caught:
            recheck_before_payment(self.buyer)
        self.assertIn('Confirm', str(caught.exception))
        order.refresh_from_db()
        self.assertEqual((order.payment_status, order.buyer_total), ('Pending', Decimal('49.00')))
        self.buyer.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('100.00'))

    def test_buyer_sees_the_whole_order_and_a_seller_sees_only_their_share(self):
        other = get_user_model().objects.create_user('other-seller@example.com', email_verified=True)
        stranger = get_user_model().objects.create_user('stranger@example.com', email_verified=True)
        first = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        second = Listing.objects.create(
            seller=other, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        Wallet.objects.create(user=self.buyer, currency='CAD', balance=Decimal('100.00'))
        Wallet.objects.create(user=self.seller, currency='CAD')
        Wallet.objects.create(user=other, currency='CAD')
        add_to_cart(self.buyer, first, 1)
        add_to_cart(self.buyer, second, 1)
        order = start_checkout(self.buyer)
        save_delivery_address(self.buyer, {
            'full_name': 'Ada Buyer', 'line1': '1 Spring Garden', 'city': 'Halifax',
            'postal_code': 'B3H 1A1', 'country': 'Canada',
        })

        shown = view_order(order, self.buyer)
        self.assertEqual(shown['payment_status'], 'Pending')
        self.assertEqual(sorted(line['listing_id'] for line in shown['lines']), sorted([first.pk, second.pk]))
        self.assertEqual(shown['buyer_total'], Decimal('54.00'))
        self.assertEqual(len(shown['seller_shares']), 2)
        self.assertEqual(shown['address']['city'], 'Halifax')

        seller_view = view_order(order, self.seller)
        self.assertEqual([line['listing_id'] for line in seller_view['lines']], [first.pk])
        self.assertEqual(seller_view['share']['share'], Decimal('27.00'))
        self.assertIsNone(seller_view['address'])
        self.assertNotIn('buyer_total', seller_view)
        self.assertNotIn(second.pk, [line['listing_id'] for line in seller_view['lines']])

        with self.assertRaises(ValidationError) as caught:
            view_order(order, stranger)
        self.assertIn('cannot view', str(caught.exception))

        order.payment_status = 'Paid'
        order.save(update_fields=['payment_status'])
        self.assertEqual(view_order(order, self.seller)['address']['city'], 'Halifax')
        self.buyer.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.balance, Decimal('100.00'))

    def test_a_guest_order_opens_only_with_its_link(self):
        listing = Listing.objects.create(
            seller=self.seller, listing_type='fixed_price', state='active', quantity=1, price='20.00', currency='CAD',
        )
        Wallet.objects.create(session_key='guest-session', currency='CAD', balance=Decimal('40.00'))
        Wallet.objects.create(user=self.seller, currency='CAD')
        add_to_cart(None, listing, 1, session_key='guest-session')
        with self.assertRaises(ValidationError):
            start_checkout(None, session_key='guest-session')
        self.assertEqual(Order.objects.count(), 0)

        order = start_checkout(None, session_key='guest-session', guest_email='guest@example.com')
        again = start_checkout(None, session_key='guest-session')
        self.assertEqual(again.pk, order.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.guest_email, 'guest@example.com')
        self.assertIsNone(order.buyer)

        with self.assertRaises(ValidationError):
            view_guest_order(email='guest@example.com')
        with self.assertRaises(ValidationError):
            view_guest_order(order_number=order.pk)
        with self.assertRaises(ValidationError):
            view_guest_order(order_number=order.pk, email='guest@example.com')
        with self.assertRaises(ValidationError):
            view_guest_order(order_number=order.pk, token='wrong-link')

        shown = view_guest_order(token=order.guest_access_token)
        self.assertEqual((shown['order_id'], shown['payment_status']), (order.pk, 'Pending'))
        self.assertEqual(shown['lines'][0]['listing_id'], listing.pk)

        account = get_user_model().objects.create_user('guest@example.com', email_verified=True)
        order.refresh_from_db()
        self.assertIsNone(order.buyer)
        with self.assertRaises(ValidationError):
            view_order(order, account)
