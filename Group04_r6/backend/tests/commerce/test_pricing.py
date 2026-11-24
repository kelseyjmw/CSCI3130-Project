from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from commerce.pricing import calculate_checkout


class CheckoutPricingTests(SimpleTestCase):
    def test_one_cad_item_adds_ten_percent_tax_and_five_delivery(self):
        quote = calculate_checkout([{
            'seller_id': 'seller1',
            'unit_price': Decimal('20.00'),
            'listing_currency': 'CAD',
            'quantity': 1,
            'seller_currency': 'CAD',
        }], 'CAD', 'CAD')

        seller = quote['sellers'][0]
        self.assertEqual(seller['seller_id'], 'seller1')
        self.assertEqual(
            (seller['item_subtotal'], seller['tax'], seller['delivery'], seller['share'], seller['credit'], seller['credit_currency']),
            (Decimal('20.00'), Decimal('2.00'), Decimal('5.00'), Decimal('27.00'), Decimal('27.00'), 'CAD'),
        )
        self.assertEqual((quote['buyer_total'], quote['buyer_currency']), (Decimal('27.00'), 'CAD'))
        self.assertEqual(
            (quote['display']['total'], quote['display']['currency']),
            (Decimal('27.00'), 'CAD'),
        )

    def test_one_seller_with_two_items_pays_delivery_once(self):
        quote = calculate_checkout([
            {
                'seller_id': 'seller1',
                'unit_price': Decimal('20.00'),
                'listing_currency': 'CAD',
                'quantity': 1,
                'seller_currency': 'CAD',
            },
            {
                'seller_id': 'seller1',
                'unit_price': Decimal('20.00'),
                'listing_currency': 'CAD',
                'quantity': 1,
                'seller_currency': 'CAD',
            },
        ], 'CAD', 'CAD')

        self.assertEqual(len(quote['sellers']), 1)
        seller = quote['sellers'][0]
        self.assertEqual(
            (seller['item_subtotal'], seller['tax'], seller['delivery'], seller['share']),
            (Decimal('40.00'), Decimal('4.00'), Decimal('5.00'), Decimal('49.00')),
        )
        self.assertEqual(quote['buyer_total'], Decimal('49.00'))

    def test_usd_item_is_charged_in_cad_and_credited_in_usd(self):
        quote = calculate_checkout([{
            'seller_id': 'seller1',
            'unit_price': Decimal('10.00'),
            'listing_currency': 'USD',
            'quantity': 1,
            'seller_currency': 'USD',
        }], 'CAD', 'CAD')

        seller = quote['sellers'][0]
        self.assertEqual(
            (seller['item_subtotal'], seller['tax'], seller['delivery'], seller['share']),
            (Decimal('14.00'), Decimal('1.40'), Decimal('5.00'), Decimal('20.40')),
        )
        self.assertEqual((quote['buyer_total'], quote['buyer_currency']), (Decimal('20.40'), 'CAD'))
        self.assertEqual((seller['credit'], seller['credit_currency']), (Decimal('14.57'), 'USD'))

    def test_display_currency_does_not_change_the_cad_charge(self):
        quote = calculate_checkout([{
            'seller_id': 'seller1',
            'unit_price': Decimal('10.00'),
            'listing_currency': 'USD',
            'quantity': 1,
            'seller_currency': 'USD',
        }], 'CAD', 'USD')

        self.assertEqual((quote['buyer_total'], quote['buyer_currency']), (Decimal('20.40'), 'CAD'))
        self.assertEqual(
            (quote['display']['item_subtotal'], quote['display']['tax'], quote['display']['delivery'], quote['display']['total'], quote['display']['currency']),
            (Decimal('10.00'), Decimal('1.00'), Decimal('3.57'), Decimal('14.57'), 'USD'),
        )

    def test_missing_rate_names_the_currencies_and_does_not_guess(self):
        with self.assertRaises(ValidationError) as caught:
            calculate_checkout([{
                'seller_id': 'seller1',
                'unit_price': Decimal('10.00'),
                'listing_currency': 'EUR',
                'quantity': 1,
                'seller_currency': 'EUR',
            }], 'CAD', 'CAD')
        self.assertIn('EUR', str(caught.exception))
        self.assertIn('CAD', str(caught.exception))
