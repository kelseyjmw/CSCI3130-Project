from datetime import timedelta
from math import ceil

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, Throttled, ValidationError

from .models import Auction, Listing, ListingStateChange
from .permissions import CanCreateListing, can_change_listing, can_create_listing, listing_is_available
from .serializers import LISTING_FIELDS, ListingPublicationSerializer
from .editing import validate_listing_edit
from .sales import sale_behavior


STATE_ACTIONS = {
    "publish": ({Listing.State.DRAFT}, Listing.State.ACTIVE),
    "pause": ({Listing.State.ACTIVE}, Listing.State.PAUSED),
    "resume": ({Listing.State.PAUSED}, Listing.State.ACTIVE),
    "end": ({Listing.State.ACTIVE, Listing.State.PAUSED}, Listing.State.ENDED),
    "remove": (set(Listing.State.values) - {Listing.State.REMOVED}, Listing.State.REMOVED),
}


@transaction.atomic
def create_listing_draft(seller, **fields):
    """Create a draft from validated fields, enforcing the per-seller limit."""
    if not seller.is_authenticated:
        raise PermissionDenied(CanCreateListing.message)

    # A no-op write locks the seller before reading the count. Unlike
    # select_for_update(), this also serializes writers on the project's SQLite.
    User = get_user_model()
    User.objects.filter(pk=seller.pk).update(account_state=F("account_state"))
    seller = User.objects.get(pk=seller.pk)
    if not can_create_listing(seller):
        raise PermissionDenied(CanCreateListing.message)

    now = timezone.now()
    recent = Listing.objects.filter(
        seller=seller, created_at__gt=now - timedelta(hours=1),
    )
    if recent.count() >= 100:
        oldest = recent.order_by("created_at").first()
        wait = ceil((oldest.created_at + timedelta(hours=1) - now).total_seconds())
        raise Throttled(wait=max(1, wait), detail="Limit of 100 listings per hour reached.")

    candidate = Listing(seller=seller, **{name: value for name, value in fields.items() if name != "minimum_bid_increment"})
    candidate.sale_behavior.validate_data(fields)
    increment = fields.pop("minimum_bid_increment", None)
    listing = Listing.objects.create(seller=seller, **fields)
    if listing.listing_type == Listing.SaleType.AUCTION:
        Auction.objects.create(listing=listing, minimum_bid_increment=increment)
    return listing


def _record_state_change(listing, new_state, actor=None):
    """The caller must hold the listing lock inside a transaction. NULL actor is System."""
    if listing.state == new_state:
        return
    old_state = listing.state
    listing.state = new_state
    listing.save()
    ListingStateChange.objects.create(
        listing=listing, old_state=old_state, new_state=new_state, actor=actor,
    )


@transaction.atomic
def _change_listing_state(listing_id, action, actor):
    if action not in STATE_ACTIONS:
        raise ValidationError("Unknown listing action.")
    if not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")

    # Lock before reads on SQLite too, and recheck current account/role restrictions.
    User = get_user_model()
    User.objects.filter(pk=actor.pk).update(account_state=F("account_state"))
    actor = get_object_or_404(User, pk=actor.pk)
    listing = _lock_listing(listing_id)
    if not can_change_listing(actor, listing, action):
        raise PermissionDenied("You do not have permission to perform this action on this listing.")
    listing.sale_behavior.validate_action(action)

    sources, target = STATE_ACTIONS[action]
    # Repeated requests are harmless and never duplicate history or publication dates.
    if listing.state == target:
        return listing
    if listing.state not in sources:
        raise ValidationError({"state": f"Cannot {action} a listing in state '{listing.state}'."})

    now = timezone.now()
    if action == "publish":
        data = {field: getattr(listing, field) for field in LISTING_FIELDS if field != "category"}
        data["category"] = listing.category_id
        serializer = ListingPublicationSerializer(
            data=data, context={"listing": listing, "publication_time": now},
        )
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            if field != "minimum_bid_increment":
                setattr(listing, field, value)
        listing.published_at = now
    elif action == "resume":
        errors = {}
        if listing.quantity is None or listing.quantity <= 0:
            errors["quantity"] = "Resuming requires stock greater than zero."
        if listing.ends_at is not None and listing.ends_at <= now:
            errors["ends_at"] = "An expired listing cannot be resumed."
        if errors:
            raise ValidationError(errors)

    if listing.listing_type == Listing.SaleType.AUCTION and action in ('end', 'remove'):
        from .auctions import cancel_auction
        cancel_auction(listing, 'Removed by an authorized reviewer.' if action == 'remove' else 'Ended by seller before any accepted bid.')
    _record_state_change(listing, target, actor)
    return listing


def _apply_automatic_state(listing, now=None):
    if listing.state in (Listing.State.DRAFT, Listing.State.REMOVED):
        return
    now = now or timezone.now()
    if listing.listing_type == Listing.SaleType.AUCTION:
        if listing.state in (Listing.State.ACTIVE, Listing.State.PAUSED) and listing.ends_at is not None and listing.ends_at <= now:
            from .auctions import complete_auction
            complete_auction(listing, now)
        return
    # Zero stock always wins over expiration, even for an already ended listing.
    if listing.quantity == 0:
        _record_state_change(listing, Listing.State.SOLD_OUT)
    elif listing.state in (Listing.State.ACTIVE, Listing.State.PAUSED) and listing.ends_at is not None and listing.ends_at <= now:
        _record_state_change(listing, Listing.State.ENDED)


def _lock_listing(listing_id):
    Listing.objects.filter(pk=listing_id).update(updated_at=F("updated_at"))
    return get_object_or_404(Listing.objects.select_related("seller", "auction"), pk=listing_id)


@transaction.atomic
def refresh_listing_state(listing_id, now=None):
    listing = _lock_listing(listing_id)
    _apply_automatic_state(listing, now)
    return listing


def change_listing_state(listing_id, action, actor):
    if action == 'remove' and Listing.objects.filter(pk=listing_id, listing_type='auction').exists():
        return _change_listing_state(listing_id, action, actor)
    # Keep automatic changes committed even when a manual action is refused.
    refresh_listing_state(listing_id)
    return _change_listing_state(listing_id, action, actor)


def process_listing_states():
    now = timezone.now()
    candidates = Listing.objects.filter(
        (Q(quantity=0) & ~Q(state__in=["draft", "removed", "sold_out"]))
        | Q(state__in=["active", "paused"], ends_at__lte=now)
    )
    count = 0
    for listing_id, before in list(candidates.values_list("pk", "state")):
        listing = refresh_listing_state(listing_id, now)
        count += listing.state != before
    return count


def _validate_quantity(quantity, minimum=0):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < minimum:
        raise ValidationError({"quantity": f"Enter a whole number of at least {minimum}."})


@transaction.atomic
def set_listing_stock(listing_id, quantity):
    listing = _lock_listing(listing_id)
    listing.sale_behavior.validate_stock(quantity)
    if quantity is not None or listing.state != Listing.State.DRAFT:
        _validate_quantity(quantity)
    if listing.state == Listing.State.REMOVED:
        raise ValidationError("Removed listings cannot be edited.")
    listing.quantity = quantity
    listing.save(update_fields=["quantity", "updated_at"])
    _apply_automatic_state(listing)
    return listing


def decrease_listing_stock(listing_id, quantity):
    """The future order workflow must call this inside its order transaction."""
    _validate_quantity(quantity, minimum=1)
    refresh_listing_state(listing_id)
    with transaction.atomic():
        listing = _lock_listing(listing_id)
        if not listing.sale_behavior.allows_direct_purchase:
            raise ValidationError("Auctions cannot be purchased at a fixed price.")
        if not listing_is_available(listing):
            raise ValidationError("This listing is not available for purchase.")
        if quantity > listing.quantity:
            raise ValidationError({"quantity": "There is not enough stock."})
        if not listing.details_locked:
            listing.details_locked_at = timezone.now()
            listing.save(update_fields=["details_locked_at"])
        return set_listing_stock(listing_id, listing.quantity - quantity)


@transaction.atomic
def update_listing_details(listing_id, fields):
    """Called with serializer-validated fields after the view's ownership check."""
    listing = _lock_listing(listing_id)
    validate_listing_edit(listing, fields=fields)
    sale_behavior(listing, fields.get("listing_type")).validate_data(
        fields, publishing=listing.state != Listing.State.DRAFT,
    )
    increment = fields.pop("minimum_bid_increment", listing.minimum_bid_increment)
    old_type = listing.listing_type
    for name, value in fields.items():
        if name != "quantity":
            setattr(listing, name, value)
    listing.save()
    if listing.listing_type == Listing.SaleType.AUCTION:
        Auction.objects.update_or_create(listing=listing, defaults={"minimum_bid_increment": increment})
    elif old_type == Listing.SaleType.AUCTION:
        Auction.objects.filter(listing=listing).delete()
    listing._state.fields_cache.pop("auction", None)
    if "quantity" in fields:
        return set_listing_stock(listing_id, fields["quantity"])
    _apply_automatic_state(listing)
    return listing
