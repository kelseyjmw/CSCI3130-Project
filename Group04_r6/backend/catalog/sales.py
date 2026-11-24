"""Sale-specific rules. Shared listing fields and permissions stay in their existing workflows."""
from django.utils import timezone
from django.db.models import Case, DecimalField, F, OuterRef, Subquery, When
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError


class SaleBehavior:
    allows_direct_purchase = True

    def __init__(self, listing):
        self.listing = listing

    def get_display_price(self):
        return self.listing.price

    @classmethod
    def price_expression(cls):
        """Database counterpart of get_display_price, used before pagination."""
        return F("price")

    def validate_data(self, attrs, publishing=False):
        raise NotImplementedError

    def validate_edit(self, fields=None, images=False):
        pass

    def validate_action(self, action):
        pass

    def validate_stock(self, quantity):
        pass


class FixedPriceBehavior(SaleBehavior):
    def validate_data(self, attrs, publishing=False):
        if attrs.get("minimum_bid_increment") is not None:
            raise ValidationError({"minimum_bid_increment": "This field applies only to auctions."})


class AuctionBehavior(SaleBehavior):
    allows_direct_purchase = False

    def get_display_price(self):
        auction = getattr(self.listing, 'auction', None)
        if auction is None:
            return self.listing.price
        order = getattr(auction, 'order', None)
        if order:
            return order.amount
        return auction.highest_bid.amount if auction.highest_bid else self.listing.price

    @classmethod
    def price_expression(cls):
        from .models import AuctionOrder, Bid
        winning_price = AuctionOrder.objects.filter(auction__listing_id=OuterRef('pk')).values('amount')[:1]
        highest_bid = Bid.objects.filter(auction__listing_id=OuterRef('pk')).order_by('-amount', 'pk').values('amount')[:1]
        return Coalesce(Subquery(winning_price), Subquery(highest_bid), F('price'),
                        output_field=DecimalField(max_digits=10, decimal_places=2))

    def validate_data(self, attrs, publishing=False):
        errors = {}
        quantity = attrs.get("quantity", self.listing.quantity)
        if quantity is None:
            attrs["quantity"] = 1
        elif quantity != 1:
            errors["quantity"] = "An auction offers exactly one item and cannot be restocked."
        increment = attrs.get("minimum_bid_increment", self.listing.minimum_bid_increment)
        if publishing and increment is None:
            errors["minimum_bid_increment"] = "A positive minimum bid increment is required."
        ends_at = attrs.get("ends_at", self.listing.ends_at)
        if publishing and ends_at is None:
            errors["ends_at"] = "Auctions require an end time."
        if ends_at is not None and (
            self.listing.published_at is None or ends_at != self.listing.ends_at
        ) and ends_at <= timezone.now():
            errors["ends_at"] = "The auction end time must be in the future."
        if errors:
            raise ValidationError(errors)

    def validate_edit(self, fields=None, images=False):
        if self.listing.details_locked:
            raise ValidationError("After the first accepted bid, auction fields, images and stock are locked.")

    def validate_action(self, action):
        if self.listing.details_locked and action in ("pause", "end"):
            raise ValidationError("An auction with an accepted bid cannot be paused or ended early.")

    def validate_stock(self, quantity):
        self.validate_edit()
        if quantity != 1:
            raise ValidationError({"quantity": "An auction offers exactly one item and cannot be restocked."})


SALE_BEHAVIORS = {"fixed_price": FixedPriceBehavior, "auction": AuctionBehavior}


def sale_behavior(listing, listing_type=None):
    behavior = SALE_BEHAVIORS[listing_type or listing.listing_type]
    return behavior(listing)


def display_price_expression():
    return Case(
        *(When(listing_type=kind, then=behavior.price_expression()) for kind, behavior in SALE_BEHAVIORS.items()),
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
