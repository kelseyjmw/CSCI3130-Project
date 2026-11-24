from decimal import Decimal

from django.core.exceptions import ValidationError

from catalog.models import Listing
from catalog.permissions import listing_is_available
from accounts.models import Wallet
from .models import Cart, CartLine
from .pricing import calculate_checkout, convert_money

SUPPORTED_CURRENCIES = {'CAD', 'USD'}


def _get_cart(buyer, session_key):
    if buyer is not None:
        return Cart.objects.filter(user=buyer).first()
    if not session_key:
        raise ValidationError('A guest cart requires a browser session.')
    return Cart.objects.filter(session_key=session_key, user__isnull=True).first()


def _get_or_create_cart(buyer, session_key):
    if buyer is not None:
        return Cart.objects.get_or_create(user=buyer)
    if not session_key:
        raise ValidationError('A guest cart requires a browser session.')
    cart = Cart.objects.filter(session_key=session_key, user__isnull=True).first()
    if cart is None:
        return Cart.objects.create(session_key=session_key), True
    return cart, False


def _require_cart_open(cart):
    if cart is not None and cart.checking_out:
        raise ValidationError('Return to the cart before changing it.')


def add_to_cart(buyer, listing, quantity, session_key=None):
    """Add a fixed-price listing to the buyer's cart."""
    if listing.listing_type != Listing.SaleType.FIXED_PRICE:
        raise ValidationError('Auction items cannot be added to the cart.')
    cart = _get_cart(buyer, session_key)
    _require_cart_open(cart)
    current = 0
    if cart is not None:
        line = cart.lines.filter(listing=listing).first()
        if line is not None:
            current = line.quantity
    available = listing.quantity if listing.quantity is not None else 0
    if current + quantity > available:
        raise ValidationError('That quantity exceeds the available stock.')
    cart, _ = _get_or_create_cart(buyer, session_key)
    line, created = CartLine.objects.get_or_create(
        cart=cart, listing=listing, defaults={'quantity': quantity},
    )
    if not created:
        line.quantity += quantity
        line.save(update_fields=['quantity'])
    return cart


def set_quantity(buyer, listing, quantity, session_key=None):
    """Replace the quantity of a listing already in the buyer's cart."""
    if quantity < 1:
        raise ValidationError('Quantity must be positive.')
    cart = _get_cart(buyer, session_key)
    _require_cart_open(cart)
    line = None if cart is None else cart.lines.filter(listing=listing).first()
    if line is None:
        raise ValidationError('That listing is not in the cart.')
    available = listing.quantity if listing.quantity is not None else 0
    if quantity > available:
        raise ValidationError('That quantity exceeds the available stock.')
    line.quantity = quantity
    line.save(update_fields=['quantity'])
    return cart


def remove_from_cart(buyer, listing, session_key=None):
    """Remove one listing from the buyer's cart."""
    cart = _get_cart(buyer, session_key)
    _require_cart_open(cart)
    if cart is not None:
        cart.lines.filter(listing=listing).delete()
    return cart


def cart_warnings(buyer, session_key=None):
    """Report cart lines that can no longer be bought. The lines stay in the cart."""
    cart = _get_cart(buyer, session_key)
    if cart is None:
        return []
    warnings = []
    for line in cart.lines.select_related('listing__seller'):
        if not listing_is_available(line.listing):
            warnings.append(f'Listing {line.listing_id} is no longer available.')
    return warnings


def set_display_currency(buyer, currency, session_key=None):
    """Select the currency used to show every price in this cart."""
    if currency not in SUPPORTED_CURRENCIES:
        raise ValidationError('CAD and USD are the supported cart currencies.')
    cart = _get_cart(buyer, session_key)
    _require_cart_open(cart)
    cart, _ = _get_or_create_cart(buyer, session_key)
    cart.display_currency = currency
    cart.save(update_fields=['display_currency'])
    return cart


def cart_display(buyer, session_key=None):
    """Return item prices and the total in the cart display currency."""
    cart = _get_cart(buyer, session_key)
    if cart is None:
        return {'currency': 'CAD', 'lines': [], 'total': Decimal('0.00')}
    rows = []
    total = Decimal('0.00')
    for line in cart.lines.select_related('listing'):
        unit_price = convert_money(line.listing.price, line.listing.currency, cart.display_currency)
        line_total = unit_price * line.quantity
        rows.append({
            'listing_id': line.listing_id,
            'quantity': line.quantity,
            'unit_price': unit_price,
            'line_total': line_total,
        })
        total += line_total
    return {'currency': cart.display_currency, 'lines': rows, 'total': total}


def _wallet_for(buyer, session_key):
    if buyer is not None:
        return Wallet.objects.filter(user=buyer).first()
    return Wallet.objects.filter(session_key=session_key, user__isnull=True).first()


def checkout_quote(buyer, session_key=None):
    """Quote the whole cart. Display currency is for the screen. The wallet is not charged."""
    cart = _get_cart(buyer, session_key)
    if cart is None or not cart.lines.exists():
        raise ValidationError('The cart is empty.')
    buyer_wallet = _wallet_for(buyer, session_key)
    if buyer_wallet is None:
        raise ValidationError('A wallet is required before checkout.')
    lines = []
    for line in cart.lines.select_related('listing__seller'):
        seller_wallet = Wallet.objects.filter(user=line.listing.seller).first()
        if seller_wallet is None:
            raise ValidationError('The seller has no wallet.')
        lines.append({
            'seller_id': line.listing.seller_id,
            'unit_price': line.listing.price,
            'listing_currency': line.listing.currency,
            'quantity': line.quantity,
            'seller_currency': seller_wallet.currency,
        })
    return calculate_checkout(lines, buyer_wallet.currency, cart.display_currency)
