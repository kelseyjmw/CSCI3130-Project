import hashlib
import secrets

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from catalog.permissions import listing_is_available, seller_can_sell
from security.permissions import user_has_permission

from .cart import _get_cart, checkout_quote
from .models import Order, OrderAddress, OrderLine, OrderSellerShare

REQUIRED_ADDRESS_FIELDS = ('full_name', 'line1', 'city', 'postal_code', 'country')


def start_checkout(buyer, session_key=None, guest_email=None):
    """Create one pending order for the whole cart, or return the order already started."""
    if buyer is not None and not user_has_permission(buyer, 'items.buy'):
        raise ValidationError('A verified, active account with permission to buy is required.')
    cart = _get_cart(buyer, session_key)
    if cart is not None:
        existing = Order.objects.filter(cart=cart, payment_status='Pending').first()
        if existing is not None:
            cart.checking_out = True
            cart.save(update_fields=['checking_out'])
            return existing
    quote = checkout_quote(buyer, session_key)
    cart = _get_cart(buyer, session_key)
    email = ''
    raw_token = None
    token_hash = None
    if cart.user is None:
        email = str(guest_email or '').strip()
        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError('A guest checkout needs an email address.')
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    order = Order.objects.create(
        cart=cart,
        buyer=cart.user,
        session_key=cart.session_key,
        payment_status='Pending',
        display_currency=quote['display']['currency'],
        display_subtotal=quote['display']['item_subtotal'],
        display_tax=quote['display']['tax'],
        display_delivery=quote['display']['delivery'],
        display_total=quote['display']['total'],
        buyer_currency=quote['buyer_currency'],
        buyer_total=quote['buyer_total'],
        guest_email=email,
        access_token_hash=token_hash,
    )
    for line in cart.lines.select_related('listing'):
        OrderLine.objects.create(
            order=order,
            listing=line.listing,
            seller=line.listing.seller,
            quantity=line.quantity,
            unit_price=line.listing.price,
            currency=line.listing.currency,
        )
    for seller in quote['sellers']:
        OrderSellerShare.objects.create(
            order=order,
            seller=get_user_model().objects.get(pk=seller['seller_id']),
            item_subtotal=seller['item_subtotal'],
            tax=seller['tax'],
            delivery=seller['delivery'],
            share=seller['share'],
            credit=seller['credit'],
            credit_currency=seller['credit_currency'],
        )
    cart.checking_out = True
    cart.save(update_fields=['checking_out'])
    if raw_token is not None:
        order.guest_access_token = raw_token
    return order


def review_checkout(buyer, session_key=None):
    """Show the current amounts. A changed total or currency must be confirmed again."""
    order, cart, quote = _pending_quote(buyer, session_key)
    display = quote['display']
    return {
        'needs_confirmation': not _quote_matches(order, cart, quote),
        'display_subtotal': display['item_subtotal'],
        'display_tax': display['tax'],
        'display_delivery': display['delivery'],
        'display_total': display['total'],
        'display_currency': display['currency'],
        'buyer_total': quote['buyer_total'],
        'buyer_currency': quote['buyer_currency'],
    }


def confirm_checkout(buyer, session_key=None):
    """Update the pending order from the current cart after the buyer confirms."""
    order, cart, quote = _pending_quote(buyer, session_key)
    if not cart.checking_out:
        raise ValidationError('Start checkout again before confirming the new amounts.')
    if _quote_matches(order, cart, quote):
        return order
    display = quote['display']
    order.display_currency = display['currency']
    order.display_subtotal = display['item_subtotal']
    order.display_tax = display['tax']
    order.display_delivery = display['delivery']
    order.display_total = display['total']
    order.buyer_currency = quote['buyer_currency']
    order.buyer_total = quote['buyer_total']
    order.save(update_fields=[
        'display_currency', 'display_subtotal', 'display_tax', 'display_delivery', 'display_total',
        'buyer_currency', 'buyer_total',
    ])
    order.lines.all().delete()
    for line in cart.lines.select_related('listing'):
        OrderLine.objects.create(
            order=order,
            listing=line.listing,
            seller=line.listing.seller,
            quantity=line.quantity,
            unit_price=line.listing.price,
            currency=line.listing.currency,
        )
    order.seller_shares.all().delete()
    for seller in quote['sellers']:
        OrderSellerShare.objects.create(
            order=order,
            seller=get_user_model().objects.get(pk=seller['seller_id']),
            item_subtotal=seller['item_subtotal'],
            tax=seller['tax'],
            delivery=seller['delivery'],
            share=seller['share'],
            credit=seller['credit'],
            credit_currency=seller['credit_currency'],
        )
    return order


def _pending_quote(buyer, session_key):
    cart = _get_cart(buyer, session_key)
    order = None if cart is None else Order.objects.filter(cart=cart, payment_status='Pending').first()
    if order is None:
        raise ValidationError('Start checkout before confirming it.')
    return order, cart, checkout_quote(buyer, session_key)


def _quote_matches(order, cart, quote):
    display = quote['display']
    amounts_match = (
        order.display_currency == display['currency']
        and order.display_subtotal == display['item_subtotal']
        and order.display_tax == display['tax']
        and order.display_delivery == display['delivery']
        and order.display_total == display['total']
        and order.buyer_currency == quote['buyer_currency']
        and order.buyer_total == quote['buyer_total']
    )
    if not amounts_match:
        return False
    saved_lines = {
        (line.listing_id, line.quantity, line.unit_price, line.currency) for line in order.lines.all()
    }
    cart_lines = {
        (line.listing_id, line.quantity, line.listing.price, line.listing.currency)
        for line in cart.lines.select_related('listing')
    }
    if saved_lines != cart_lines:
        return False
    saved_shares = {
        (share.seller_id, share.item_subtotal, share.tax, share.delivery, share.share, share.credit, share.credit_currency)
        for share in order.seller_shares.all()
    }
    quote_shares = {
        (seller['seller_id'], seller['item_subtotal'], seller['tax'], seller['delivery'], seller['share'], seller['credit'], seller['credit_currency'])
        for seller in quote['sellers']
    }
    return saved_shares == quote_shares


def recheck_before_payment(buyer, session_key=None):
    """Recheck the pending order before payment. The wallet is not charged."""
    cart = _get_cart(buyer, session_key)
    order = None if cart is None else Order.objects.filter(cart=cart, payment_status='Pending').first()
    if order is None:
        raise ValidationError('Start checkout before payment.')
    if buyer is not None and not user_has_permission(buyer, 'items.buy'):
        raise ValidationError('A verified, active account with permission to buy is required.')
    if not cart.checking_out:
        raise ValidationError('Start checkout again before payment.')
    for line in cart.lines.select_related('listing__seller'):
        listing = line.listing
        if buyer is not None and listing.seller_id == buyer.pk:
            raise ValidationError(f'You cannot buy your own listing {listing.pk}.')
        if not seller_can_sell(listing.seller):
            raise ValidationError(f'The seller of listing {listing.pk} cannot sell.')
        if not listing_is_available(listing):
            raise ValidationError(f'Listing {listing.pk} is no longer available. Remove it before payment.')
        available = listing.quantity if listing.quantity is not None else 0
        if line.quantity > available:
            raise ValidationError(f'Listing {listing.pk} does not have enough stock. Correct the quantity before payment.')
    if not _quote_matches(order, cart, checkout_quote(buyer, session_key)):
        raise ValidationError('Confirm the new amounts before payment.')
    return order


def return_to_cart(buyer, session_key=None):
    """Unlock the cart so the buyer can change it. Checkout must be started again."""
    cart = _get_cart(buyer, session_key)
    if cart is None:
        return None
    cart.checking_out = False
    cart.save(update_fields=['checking_out'])
    return cart


def save_delivery_address(buyer, address, session_key=None):
    """Save a copy of the delivery address on the pending order."""
    missing = [name for name in REQUIRED_ADDRESS_FIELDS if not str(address.get(name, '')).strip()]
    if missing:
        raise ValidationError('A delivery address needs a full name, address line, city, postal code, and country.')
    cart = _get_cart(buyer, session_key)
    order = None if cart is None else Order.objects.filter(cart=cart, payment_status='Pending').first()
    if order is None:
        raise ValidationError('Start checkout before entering a delivery address.')
    OrderAddress.objects.update_or_create(
        order=order,
        defaults={
            'full_name': address['full_name'].strip(),
            'line1': address['line1'].strip(),
            'line2': str(address.get('line2', '')).strip(),
            'city': address['city'].strip(),
            'region': str(address.get('region', '')).strip(),
            'postal_code': address['postal_code'].strip(),
            'country': address['country'].strip(),
        },
    )
    return order


def view_order(order, viewer):
    """Return the part of an order this user is allowed to see."""
    if viewer is not None and order.buyer_id == viewer.pk:
        return _buyer_order_view(order)
    share = None if viewer is None else order.seller_shares.filter(seller=viewer).first()
    if share is None:
        raise ValidationError('You cannot view this order.')
    return {
        'order_id': order.pk,
        'payment_status': order.payment_status,
        'lines': [_line_dict(line) for line in order.lines.filter(seller=viewer)],
        'share': _share_dict(share),
        'address': _address_dict(order) if order.payment_status == 'Paid' else None,
    }


def view_guest_order(order_number=None, email=None, token=None):
    """Open a guest order from its unguessable link. An email or order number is not enough."""
    if not token:
        raise ValidationError('An order number or email address does not open this order.')
    order = Order.objects.filter(access_token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if order is None or (order_number is not None and order.pk != order_number):
        raise ValidationError('That order link is not valid.')
    return _buyer_order_view(order)


def _buyer_order_view(order):
    return {
        'order_id': order.pk,
        'payment_status': order.payment_status,
        'lines': [_line_dict(line) for line in order.lines.all()],
        'seller_shares': [_share_dict(share) for share in order.seller_shares.all()],
        'display_subtotal': order.display_subtotal,
        'display_tax': order.display_tax,
        'display_delivery': order.display_delivery,
        'display_total': order.display_total,
        'display_currency': order.display_currency,
        'buyer_total': order.buyer_total,
        'buyer_currency': order.buyer_currency,
        'address': _address_dict(order),
    }


def _line_dict(line):
    return {
        'listing_id': line.listing_id,
        'seller_id': line.seller_id,
        'quantity': line.quantity,
        'unit_price': line.unit_price,
        'currency': line.currency,
    }


def _share_dict(share):
    return {
        'seller_id': share.seller_id,
        'item_subtotal': share.item_subtotal,
        'tax': share.tax,
        'delivery': share.delivery,
        'share': share.share,
        'credit': share.credit,
        'credit_currency': share.credit_currency,
    }


def _address_dict(order):
    address = OrderAddress.objects.filter(order=order).first()
    if address is None:
        return None
    return {
        'full_name': address.full_name,
        'line1': address.line1,
        'line2': address.line2,
        'city': address.city,
        'region': address.region,
        'postal_code': address.postal_code,
        'country': address.country,
    }
