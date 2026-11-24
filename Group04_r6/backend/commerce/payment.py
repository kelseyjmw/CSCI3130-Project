from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import Wallet, WalletTransaction
from catalog.models import AuctionOrder, Listing
from catalog.permissions import seller_can_sell
from catalog.services import _record_state_change
from security.permissions import user_has_permission

from .checkout import REQUIRED_ADDRESS_FIELDS, recheck_before_payment
from .models import AuctionOrderSettlement, Order, OrderAddress
from .pricing import calculate_checkout


def _lock_buyer_wallet(buyer, session_key):
    if buyer is not None:
        wallet = Wallet.objects.select_for_update().filter(user=buyer).first()
    else:
        if not session_key:
            raise ValidationError('A guest payment requires a browser session.')
        wallet = Wallet.objects.select_for_update().filter(session_key=session_key, user__isnull=True).first()
    if wallet is None:
        raise ValidationError('A wallet is required before payment.')
    return wallet


def _validate_order_owner(order, buyer, session_key):
    if buyer is not None:
        if order.buyer_id != buyer.pk:
            raise ValidationError('You cannot pay for this order.')
    else:
        if order.buyer_id is not None or not session_key or order.session_key != session_key:
            raise ValidationError('You cannot pay for this order.')


@transaction.atomic
def pay_order(order_id, buyer, session_key=None):
    """Settle a pending cart order atomically using buyer and seller wallets."""
    if buyer is not None and not getattr(buyer, 'is_authenticated', False):
        buyer = None

    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        raise ValidationError('Order not found.')

    _validate_order_owner(order, buyer, session_key)

    if order.payment_status == 'Paid':
        return {
            'order_id': order.pk,
            'payment_status': 'Paid',
            'already_paid': True,
        }

    if order.payment_status != 'Pending':
        raise ValidationError('Only pending orders can be paid.')

    if buyer is not None and not user_has_permission(buyer, 'items.buy'):
        raise ValidationError('A verified, active account with permission to buy is required.')

    if not OrderAddress.objects.filter(order=order).exists():
        raise ValidationError('A delivery address is required before payment.')

    # Lock listings and wallets in deterministic primary-key order before validation and mutation.
    lines = list(order.lines.select_related('listing').order_by('listing_id'))
    shares = list(order.seller_shares.order_by('seller_id'))

    listing_ids = sorted({line.listing_id for line in lines})
    locked_listings = {
        listing.pk: listing
        for listing in Listing.objects.select_for_update().filter(pk__in=listing_ids).order_by('pk')
    }

    buyer_wallet = _lock_buyer_wallet(buyer, session_key)
    seller_ids = sorted({share.seller_id for share in shares})
    locked_seller_wallets = {
        wallet.user_id: wallet
        for wallet in Wallet.objects.select_for_update().filter(user_id__in=seller_ids).order_by('pk')
    }

    # Re-verify buyer/seller eligibility, listing availability, stock, and unchanged quote.
    recheck_before_payment(buyer, session_key)

    if buyer_wallet.currency != order.buyer_currency:
        raise ValidationError('Wallet currency does not match the order currency.')

    if buyer_wallet.balance < order.buyer_total:
        raise ValidationError('Insufficient wallet balance to complete payment.')

    for share in shares:
        seller_wallet = locked_seller_wallets.get(share.seller_id)
        if seller_wallet is None:
            raise ValidationError('The seller has no wallet.')
        if seller_wallet.currency != share.credit_currency:
            raise ValidationError('Seller wallet currency changed before payment.')

    # 1. Debit buyer wallet and record transaction.
    buyer_wallet.balance -= order.buyer_total
    buyer_wallet.save(update_fields=['balance'])
    WalletTransaction.objects.create(
        wallet=buyer_wallet,
        transaction_type=WalletTransaction.TransactionType.PAYMENT,
        amount=order.buyer_total,
        currency=buyer_wallet.currency,
        resulting_balance=buyer_wallet.balance,
        reference=f'Order #{order.pk}',
    )

    # 2. Credit each seller wallet in their own currency and record receipt transaction.
    for share in shares:
        seller_wallet = locked_seller_wallets[share.seller_id]
        seller_wallet.balance += share.credit
        seller_wallet.save(update_fields=['balance'])
        WalletTransaction.objects.create(
            wallet=seller_wallet,
            transaction_type=WalletTransaction.TransactionType.RECEIPT,
            amount=share.credit,
            currency=seller_wallet.currency,
            resulting_balance=seller_wallet.balance,
            reference=f'Order #{order.pk}',
        )

    # 3. Deduct fixed-price stock and transition to Sold out when stock reaches zero.
    for line in lines:
        listing = locked_listings[line.listing_id]
        available = listing.quantity if listing.quantity is not None else 0
        if line.quantity > available:
            raise ValidationError(f'Listing {listing.pk} does not have enough stock.')
        listing.quantity = available - line.quantity
        if listing.quantity == 0:
            _record_state_change(listing, Listing.State.SOLD_OUT)
        else:
            listing.save(update_fields=['quantity', 'updated_at'])

    # 4. Mark order Paid and clear/unlock the cart.
    order.payment_status = 'Paid'
    order.save(update_fields=['payment_status'])

    cart = order.cart
    cart.lines.all().delete()
    cart.checking_out = False
    cart.save(update_fields=['checking_out'])

    return {
        'order_id': order.pk,
        'payment_status': 'Paid',
        'already_paid': False,
    }


def _validate_auction_buyer_and_quote(auction_order, buyer):
    if buyer is None or not getattr(buyer, 'is_authenticated', False):
        raise ValidationError('You must sign in to pay for an auction win.')
    if auction_order.buyer_id != buyer.pk:
        raise ValidationError('Only the winning buyer can pay for this auction order.')
    if auction_order.seller_id == buyer.pk:
        raise ValidationError('You cannot buy your own auction listing.')
    if not user_has_permission(buyer, 'items.buy'):
        raise ValidationError('A verified, active account with permission to buy is required.')
    if not seller_can_sell(auction_order.seller):
        raise ValidationError('The seller cannot complete this sale.')

    buyer_wallet = Wallet.objects.filter(user=buyer).first()
    if buyer_wallet is None:
        raise ValidationError('A wallet is required before payment.')
    seller_wallet = Wallet.objects.filter(user=auction_order.seller).first()
    if seller_wallet is None:
        raise ValidationError('The seller has no wallet.')

    quote = calculate_checkout(
        [{
            'seller_id': auction_order.seller_id,
            'unit_price': auction_order.amount,
            'listing_currency': auction_order.currency,
            'quantity': auction_order.quantity,
            'seller_currency': seller_wallet.currency,
        }],
        buyer_wallet.currency,
        buyer_wallet.currency,
    )
    return quote


def quote_auction_order(auction_order_id, buyer):
    """Quote tax, delivery, and total for a won auction order without charging the wallet."""
    auction_order = AuctionOrder.objects.select_related('seller', 'buyer').filter(pk=auction_order_id).first()
    if auction_order is None:
        raise ValidationError('Auction order not found.')
    quote = _validate_auction_buyer_and_quote(auction_order, buyer)
    seller_share = quote['sellers'][0]
    return {
        'auction_order_id': auction_order.pk,
        'payment_status': auction_order.payment_status,
        'item_subtotal': seller_share['item_subtotal'],
        'tax': seller_share['tax'],
        'delivery': seller_share['delivery'],
        'buyer_total': quote['buyer_total'],
        'buyer_currency': quote['buyer_currency'],
        'seller_credit': seller_share['credit'],
        'seller_currency': seller_share['credit_currency'],
    }


@transaction.atomic
def pay_auction_order(auction_order_id, buyer, address):
    """Settle a pending Release 5 auction order atomically without touching the cart or listing stock."""
    if buyer is None or not getattr(buyer, 'is_authenticated', False):
        raise ValidationError('You must sign in to pay for an auction win.')

    auction_order = (
        AuctionOrder.objects
        .select_for_update()
        .select_related('seller', 'buyer', 'auction__listing')
        .filter(pk=auction_order_id)
        .first()
    )
    if auction_order is None:
        raise ValidationError('Auction order not found.')

    if auction_order.buyer_id != buyer.pk:
        raise ValidationError('Only the winning buyer can pay for this auction order.')

    if auction_order.payment_status == 'Paid':
        return {
            'auction_order_id': auction_order.pk,
            'payment_status': 'Paid',
            'already_paid': True,
        }

    if auction_order.payment_status != 'Pending':
        raise ValidationError('Only pending auction orders can be paid.')

    if not isinstance(address, dict):
        raise ValidationError('A delivery address is required before payment.')
    missing = [name for name in REQUIRED_ADDRESS_FIELDS if not str(address.get(name, '')).strip()]
    if missing:
        raise ValidationError('A delivery address needs a full name, address line, city, postal code, and country.')

    # Lock both wallets in deterministic pk order.
    wallet_user_ids = sorted({buyer.pk, auction_order.seller_id})
    locked_wallets = {
        w.user_id: w
        for w in Wallet.objects.select_for_update().filter(user_id__in=wallet_user_ids).order_by('pk')
    }

    quote = _validate_auction_buyer_and_quote(auction_order, buyer)
    buyer_wallet = locked_wallets.get(buyer.pk)
    seller_wallet = locked_wallets.get(auction_order.seller_id)
    if buyer_wallet is None:
        raise ValidationError('A wallet is required before payment.')
    if seller_wallet is None:
        raise ValidationError('The seller has no wallet.')

    if buyer_wallet.balance < quote['buyer_total']:
        raise ValidationError('Insufficient wallet balance to pay for this auction win.')

    seller_share = quote['sellers'][0]

    # 1. Debit buyer wallet.
    buyer_wallet.balance -= quote['buyer_total']
    buyer_wallet.save(update_fields=['balance'])
    WalletTransaction.objects.create(
        wallet=buyer_wallet,
        transaction_type=WalletTransaction.TransactionType.PAYMENT,
        amount=quote['buyer_total'],
        currency=buyer_wallet.currency,
        resulting_balance=buyer_wallet.balance,
        reference=f'AuctionOrder #{auction_order.pk}',
    )

    # 2. Credit seller wallet in seller's wallet currency.
    seller_wallet.balance += seller_share['credit']
    seller_wallet.save(update_fields=['balance'])
    WalletTransaction.objects.create(
        wallet=seller_wallet,
        transaction_type=WalletTransaction.TransactionType.RECEIPT,
        amount=seller_share['credit'],
        currency=seller_wallet.currency,
        resulting_balance=seller_wallet.balance,
        reference=f'AuctionOrder #{auction_order.pk}',
    )

    # 3. Record immutable settlement details and delivery address, and mark AuctionOrder Paid.
    AuctionOrderSettlement.objects.create(
        auction_order=auction_order,
        item_subtotal=seller_share['item_subtotal'],
        tax=seller_share['tax'],
        delivery=seller_share['delivery'],
        buyer_total=quote['buyer_total'],
        buyer_currency=quote['buyer_currency'],
        seller_credit=seller_share['credit'],
        seller_currency=seller_share['credit_currency'],
        full_name=address['full_name'].strip(),
        line1=address['line1'].strip(),
        line2=str(address.get('line2', '')).strip(),
        city=address['city'].strip(),
        region=str(address.get('region', '')).strip(),
        postal_code=address['postal_code'].strip(),
        country=address['country'].strip(),
    )

    auction_order.payment_status = 'Paid'
    auction_order.save(update_fields=['payment_status'])

    return {
        'auction_order_id': auction_order.pk,
        'payment_status': 'Paid',
        'already_paid': False,
    }


def view_auction_order(auction_order_id, viewer):
    """Return role-scoped details for an auction order; seller sees address only after Paid."""
    auction_order = (
        AuctionOrder.objects
        .select_related('auction__listing', 'seller', 'buyer')
        .filter(pk=auction_order_id)
        .first()
    )
    if auction_order is None:
        raise ValidationError('Auction order not found.')
    if viewer is None or not getattr(viewer, 'is_authenticated', False):
        raise ValidationError('You cannot view this auction order.')
    if viewer.pk not in (auction_order.buyer_id, auction_order.seller_id):
        raise ValidationError('You cannot view this auction order.')

    settlement = AuctionOrderSettlement.objects.filter(auction_order=auction_order).first()
    address = None
    if settlement is not None and (viewer.pk == auction_order.buyer_id or auction_order.payment_status == 'Paid'):
        address = {
            'full_name': settlement.full_name,
            'line1': settlement.line1,
            'line2': settlement.line2,
            'city': settlement.city,
            'region': settlement.region,
            'postal_code': settlement.postal_code,
            'country': settlement.country,
        }

    return {
        'auction_order_id': auction_order.pk,
        'listing_id': auction_order.auction.listing_id,
        'payment_status': auction_order.payment_status,
        'winning_amount': auction_order.amount,
        'winning_currency': auction_order.currency,
        'buyer_total': settlement.buyer_total if settlement else None,
        'buyer_currency': settlement.buyer_currency if settlement else None,
        'seller_credit': settlement.seller_credit if settlement else None,
        'seller_currency': settlement.seller_currency if settlement else None,
        'address': address,
    }