from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Wallet
from catalog.models import Listing
from commerce.cart import add_to_cart
from commerce.models import Cart
from security.permissions import assign_buyer, grant_seller


class CartApiTests(TestCase):
    def setUp(self):
        user = get_user_model()
        self.client = APIClient()
        self.seller = user.objects.create_user('seller@example.com', email_verified=True)
        self.buyer = user.objects.create_user('buyer@example.com', email_verified=True)
        assign_buyer(self.buyer)
        grant_seller(self.seller)
        self.listing = Listing.objects.create(
            seller=self.seller, title='Desk lamp', listing_type='fixed_price', state='active',
            quantity=2, price='20.00', currency='CAD',
        )

    def test_member_sees_the_saved_cart(self):
        add_to_cart(self.buyer, self.listing, 1)
        self.client.force_authenticate(self.buyer)

        response = self.client.get('/api/commerce/cart/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['currency'], 'CAD')
        self.assertEqual(response.data['total'], '20.00')
        self.assertEqual(response.data['warnings'], [])
        self.assertFalse(response.data['checking_out'])
        self.assertEqual(response.data['lines'], [{
            'listing_id': self.listing.pk,
            'title': 'Desk lamp',
            'quantity': 1,
            'unit_price': '20.00',
            'line_total': '20.00',
        }])

    def test_an_empty_cart_does_not_create_one(self):
        self.client.force_authenticate(self.buyer)

        response = self.client.get('/api/commerce/cart/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['lines'], [])
        self.assertEqual(response.data['total'], '0.00')
        self.assertFalse(Cart.objects.filter(user=self.buyer).exists())

    def test_guest_cart_uses_the_browser_session(self):
        session = self.client.session
        session.save()
        add_to_cart(None, self.listing, 2, session_key=session.session_key)

        response = self.client.get('/api/commerce/cart/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['lines'][0]['quantity'], 2)
        self.assertEqual(response.data['total'], '40.00')

    def test_cart_actions_and_checkout_use_the_same_services(self):
        Wallet.objects.create(user=self.buyer, currency='CAD', balance='100.00')
        Wallet.objects.create(user=self.seller, currency='CAD')
        self.client.force_authenticate(self.buyer)

        added = self.client.post('/api/commerce/cart/items/', {'listing_id': self.listing.pk, 'quantity': 1}, format='json')
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.data['lines'][0]['quantity'], 1)
        changed = self.client.patch('/api/commerce/cart/items/', {'listing_id': self.listing.pk, 'quantity': 2}, format='json')
        self.assertEqual(changed.data['lines'][0]['quantity'], 2)
        currency = self.client.post('/api/commerce/cart/currency/', {'currency': 'USD'}, format='json')
        self.assertEqual(currency.data['currency'], 'USD')
        rejected = self.client.post('/api/commerce/cart/currency/', {'currency': 'EUR'}, format='json')
        self.assertEqual(rejected.status_code, 400)

        started = self.client.post('/api/commerce/checkout/', {}, format='json')
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.data['buyer_currency'], 'CAD')
        self.assertTrue(started.data['buyer_total'])
        locked = self.client.patch('/api/commerce/cart/items/', {'listing_id': self.listing.pk, 'quantity': 1}, format='json')
        self.assertEqual(locked.status_code, 400)

        address = self.client.post('/api/commerce/checkout/address/', {
            'full_name': 'Ada Buyer', 'line1': '1 Spring Garden', 'city': 'Halifax',
            'postal_code': 'B3H 1A1', 'country': 'Canada',
        }, format='json')
        self.assertEqual(address.status_code, 200)
        confirmed = self.client.post('/api/commerce/checkout/confirm/', {}, format='json')
        self.assertEqual(confirmed.status_code, 200)
        self.assertFalse(confirmed.data['needs_confirmation'])

        order_id = started.data['order_id']
        visible = self.client.get(f'/api/commerce/orders/{order_id}/')
        self.assertEqual(visible.status_code, 200)
        self.assertEqual(visible.data['payment_status'], 'Pending')
        self.assertEqual(visible.data['address']['city'], 'Halifax')
        self.assertEqual(len(visible.data['lines']), 1)

        stranger = APIClient()
        stranger.force_authenticate(get_user_model().objects.create_user('stranger@example.com', email_verified=True))
        self.assertEqual(stranger.get(f'/api/commerce/orders/{order_id}/').status_code, 403)

        opened = self.client.post('/api/commerce/checkout/return/', {}, format='json')
        self.assertFalse(opened.data['checking_out'])
        removed = self.client.delete(f'/api/commerce/cart/items/{self.listing.pk}/')
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data['lines'], [])

    def test_guest_checkout_link_opens_the_order(self):
        Wallet.objects.create(user=self.seller, currency='CAD')
        guest = APIClient()
        added = guest.post('/api/commerce/cart/items/', {'listing_id': self.listing.pk, 'quantity': 1}, format='json')
        self.assertEqual(added.status_code, 200)
        Wallet.objects.create(session_key=guest.session.session_key, currency='CAD', balance='40.00')
        refused = guest.post('/api/commerce/checkout/', {}, format='json')
        self.assertEqual(refused.status_code, 400)

        started = guest.post('/api/commerce/checkout/', {'guest_email': 'guest@example.com'}, format='json')
        self.assertEqual(started.status_code, 200)
        token = started.data['guest_access_token']
        self.assertTrue(token)
        opened = guest.get(f'/api/commerce/orders/guest/{token}/')
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.data['order_id'], started.data['order_id'])
        self.assertEqual(opened.data['payment_status'], 'Pending')
        self.assertEqual(APIClient().get('/api/commerce/orders/guest/not-a-real-link/').status_code, 404)
