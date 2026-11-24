from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

# CAD to USD is 1 / 1.40 and the money result is rounded to the nearest cent.
RATES = {
    ('USD', 'CAD'): Decimal('1.40'),
    ('CAD', 'USD'): Decimal('1') / Decimal('1.40'),
}


def convert_money(amount, source, target):
    if source == target:
        return amount
    rate = RATES.get((source, target))
    if rate is None:
        raise ValidationError(f'No conversion rate is stored from {source} to {target}.')
    converted = amount * rate
    return converted.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_checkout(lines, buyer_currency, display_currency):
    """Quote tax, delivery and the buyer total for one checkout."""
    subtotals = {}
    seller_currencies = {}
    seller_order = []
    for line in lines:
        seller_id = line['seller_id']
        if seller_id not in subtotals:
            subtotals[seller_id] = Decimal('0.00')
            seller_currencies[seller_id] = line['seller_currency']
            seller_order.append(seller_id)
        item_subtotal = convert_money(line['unit_price'] * line['quantity'], line['listing_currency'], buyer_currency)
        subtotals[seller_id] += item_subtotal

    sellers = []
    buyer_total = Decimal('0.00')
    for seller_id in seller_order:
        subtotal = subtotals[seller_id]
        tax = (subtotal * Decimal('0.10')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        delivery = Decimal('5.00')
        share = subtotal + tax + delivery
        credit = convert_money(share, buyer_currency, seller_currencies[seller_id])
        buyer_total += share
        sellers.append({
            'seller_id': seller_id,
            'item_subtotal': subtotal,
            'tax': tax,
            'delivery': delivery,
            'share': share,
            'credit': credit,
            'credit_currency': seller_currencies[seller_id],
        })
    display_subtotal = Decimal('0.00')
    display_tax = Decimal('0.00')
    display_delivery = Decimal('0.00')
    for seller in sellers:
        display_subtotal += convert_money(seller['item_subtotal'], buyer_currency, display_currency)
        display_tax += convert_money(seller['tax'], buyer_currency, display_currency)
        display_delivery += convert_money(seller['delivery'], buyer_currency, display_currency)
    return {
        'buyer_total': buyer_total,
        'buyer_currency': buyer_currency,
        'sellers': sellers,
        'display': {
            'item_subtotal': display_subtotal,
            'tax': display_tax,
            'delivery': display_delivery,
            'total': convert_money(buyer_total, buyer_currency, display_currency),
            'currency': display_currency,
        },
    }
