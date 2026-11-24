"""Serialized bidding and completion, using the existing listing write lock."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from security.permissions import user_has_permission
from .models import Auction, AuctionNotification, AuctionOrder, Bid, BidIneligibility, Listing
from .permissions import seller_can_sell


def can_bid(user, listing):
    return (
        user.is_authenticated and user.pk != listing.seller_id
        and user_has_permission(user, 'items.buy')
        and user.account_state == 'Active'
    )


def cancel_auction(listing, reason):
    """Caller holds the listing lock. Completed sales are never rewritten."""
    auction = listing.auction
    if auction.completed_at is None:
        auction.completed_at = timezone.now()
        auction.completion_reason = reason
        auction.save(update_fields=['completed_at', 'completion_reason'])


def complete_auction(listing, now):
    """Called inside refresh_listing_state's transaction, before general expiry."""
    from .services import _record_state_change
    auction = listing.auction
    if auction.completed_at is not None:
        return
    winner = None
    if seller_can_sell(listing.seller):
        for bid in auction.bids.filter(ineligibility__isnull=True).select_related('buyer').order_by('-amount', 'pk'):
            if can_bid(bid.buyer, listing):
                winner = bid
                break
            BidIneligibility.objects.get_or_create(bid=bid, defaults={'reason': 'Buyer was not eligible at completion.'})
    auction.completed_at = now
    auction.completion_reason = 'Highest eligible bid wins.' if winner else 'Ended without an eligible winner.'
    auction.save(update_fields=['completed_at', 'completion_reason'])
    if winner is None:
        _record_state_change(listing, Listing.State.ENDED)
        AuctionNotification.objects.create(
            recipient=listing.seller, auction=auction,
            message=f'Your auction ended: {listing.title}. No eligible winner or order was created.',
        )
        from .emails import send_auction_end_notification
        transaction.on_commit(lambda: send_auction_end_notification(listing.seller.email, auction), robust=True)
        return
    order = AuctionOrder.objects.create(
        auction=auction, winning_bid=winner, seller=listing.seller, buyer=winner.buyer,
        amount=winner.amount, currency=winner.currency, quantity=1, payment_status='Pending',
    )
    listing.quantity = 0
    _record_state_change(listing, Listing.State.SOLD_OUT)
    for recipient, prefix in ((winner.buyer, 'You won'), (listing.seller, 'Your auction sold')):
        AuctionNotification.objects.create(
            recipient=recipient, auction=auction, order=order,
            message=f'{prefix}: {listing.title}. Winning price: {order.currency} {order.amount:.2f}. '
                    f'Order #{order.pk}, quantity 1, payment Pending.',
        )
    from .emails import send_auction_end_notification, send_auction_winner_notification
    transaction.on_commit(lambda: send_auction_end_notification(listing.seller.email, auction), robust=True)
    transaction.on_commit(lambda: send_auction_winner_notification(winner.buyer.email, auction), robust=True)


def submit_bid(listing_id, buyer, amount, currency=None):
    from .services import refresh_listing_state
    if not buyer.is_authenticated:
        raise PermissionDenied('Log in to place a bid.')
    # Commit any due completion even when the bid is subsequently rejected.
    refresh_listing_state(listing_id)
    return _accept_bid(listing_id, buyer.pk, amount, currency)


@transaction.atomic
def _accept_bid(listing_id, buyer_id, amount, currency):
    from .services import _lock_listing
    listing = _lock_listing(listing_id)
    buyer = get_user_model().objects.get(pk=buyer_id)
    if listing.listing_type != Listing.SaleType.AUCTION:
        raise ValidationError('Only auction listings accept bids.')
    if not can_bid(buyer, listing):
        raise PermissionDenied('An active, verified buyer with permission to buy is required. Sellers cannot bid on their own items.')
    if (listing.state != Listing.State.ACTIVE or listing.auction.completed_at is not None
            or not seller_can_sell(listing.seller)):
        raise ValidationError('This auction is not available for bidding.')
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01')).run_validation(amount)
    if currency is not None and (not isinstance(currency, str) or currency.upper() != listing.currency):
        raise ValidationError({'currency': 'Bids must use the listing currency.'})
    minimum = listing.auction.minimum_next_bid
    if amount < minimum:
        raise ValidationError({
            'detail': f'The minimum permitted bid is {listing.currency} {minimum:.2f}.',
            'minimum_bid': f'{minimum:.2f}', 'currency': listing.currency,
        })
    accepted_at = timezone.now()
    if listing.ends_at is None or accepted_at >= listing.ends_at:
        raise ValidationError('The auction has ended. Bids at or after its end time are refused.')
    bid = Bid.objects.create(auction=listing.auction, buyer=buyer, amount=amount,
                             currency=listing.currency, created_at=accepted_at)
    if listing.details_locked_at is None:
        listing.details_locked_at = accepted_at
        listing.save(update_fields=['details_locked_at', 'updated_at'])
    return bid


@transaction.atomic
def handle_account_suspension(user_id):
    from .services import _lock_listing, _record_state_change
    # All writes are serialized by SQLite; use the same listing locks as bidding/completion.
    for listing_id in Listing.objects.filter(
        seller_id=user_id, listing_type='auction', state__in=['active', 'paused'],
        auction__completed_at__isnull=True,
    ).order_by('pk').values_list('pk', flat=True):
        listing = _lock_listing(listing_id)
        if listing.auction.completed_at is None:
            cancel_auction(listing, 'Seller suspended before completion. Auction cancelled without a sale.')
            _record_state_change(listing, Listing.State.ENDED)
    bids = Bid.objects.filter(buyer_id=user_id, auction__completed_at__isnull=True, ineligibility__isnull=True)
    for bid in bids:
        BidIneligibility.objects.get_or_create(bid=bid, defaults={'reason': 'Buyer suspended before completion.'})
