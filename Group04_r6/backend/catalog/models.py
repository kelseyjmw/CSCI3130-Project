from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.functional import cached_property

from .validators import validate_country_code, validate_currency_code


class Category(models.Model):
    name = models.CharField(max_length=100)

    parent = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        related_name="children",
        on_delete=models.PROTECT,
    )

    @property
    def is_leaf(self):
        return not self.children.exists()

    def __str__(self):
        return self.name


class CategoryAttribute(models.Model):
    class Type(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        CHOICE = "choice", "Choice"

    category = models.ForeignKey(
        Category,
        related_name="attributes",
        on_delete=models.PROTECT,
    )

    name = models.CharField(max_length=100)
    code = models.SlugField(unique=True)

    type = models.CharField(
        max_length=10,
        choices=Type.choices,
    )

    required = models.BooleanField(default=False)
    filterable = models.BooleanField(default=False)

    min_value = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
    )

    max_value = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
    )

    options = models.JSONField(default=list, blank=True)


class ListingQuerySet(models.QuerySet):
    def with_display_price(self):
        from .sales import display_price_expression
        return self.annotate(_display_price=display_price_expression())

    def delete(self):
        raise ValidationError("Listings must be removed by changing their state, not deleted.")


class Listing(models.Model):
    objects = ListingQuerySet.as_manager()

    class SaleType(models.TextChoices):
        FIXED_PRICE = "fixed_price", "Fixed price"
        AUCTION = "auction", "Auction"

    listing_type = models.CharField(max_length=20, choices=SaleType.choices, default=SaleType.FIXED_PRICE)

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="listings",
    )
    title = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="listings",
        null=True,
        blank=True,
    )
    attribute_values = models.JSONField(
        default=dict,
        blank=True,
    )

    country = models.CharField(
        max_length=2,
        blank=True,
        validators=[validate_country_code],
    )
    postal_code = models.CharField(
        max_length=20,
        blank=True,
    )

    currency = models.CharField(
        max_length=3,
        blank=True,
        validators=[validate_currency_code],
    )

    class Condition(models.TextChoices):
        NEW = "new", "New"
        NEW_NO_PACKAGE = "new_no_package", "New, no package"
        REFURBISHED = "refurbished", "Refurbished"
        USED_VERY_GOOD = "used_very_good", "Used, very good"
        USED_GOOD = "used_good", "Used, good"
        FOR_PARTS = "for_parts", "For parts"

    condition = models.CharField(
        max_length=20,
        choices=Condition.choices,
        blank=True,
    )

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        SOLD_OUT = "sold_out", "Sold out"
        ENDED = "ended", "Ended"
        REMOVED = "removed", "Removed"

    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.DRAFT,
    )

    # Drafts may omit stock; publication requires at least one item.
    quantity = models.PositiveIntegerField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    details_locked_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0) | models.Q(quantity__isnull=True),
                name="listing_quantity_nonnegative",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def details_locked(self):
        if self.details_locked_at is not None:
            return True
        auction = getattr(self, 'auction', None) if self.listing_type == self.SaleType.AUCTION else None
        return auction is not None and auction.highest_bid is not None

    @property
    def sale_behavior(self):
        from .sales import sale_behavior
        return sale_behavior(self)

    def get_display_price(self):
        if "_display_price" in self.__dict__:
            return self._display_price
        return self.sale_behavior.get_display_price()

    @property
    def minimum_bid_increment(self):
        auction = getattr(self, "auction", None)
        return auction.minimum_bid_increment if auction else None

    def delete(self, *args, **kwargs):
        raise ValidationError("Listings must be removed by changing their state, not deleted.")


class Auction(models.Model):
    listing = models.OneToOneField(Listing, on_delete=models.PROTECT, related_name="auction")
    # Drafts may omit the increment; publication requires a positive value.
    minimum_bid_increment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    completion_reason = models.CharField(max_length=200, blank=True, editable=False)

    @cached_property
    def highest_bid(self):
        return self.bids.order_by('-amount', 'pk').first()

    @property
    def minimum_next_bid(self):
        if self.highest_bid is None:
            return self.listing.price
        return self.highest_bid.amount + self.minimum_bid_increment

    class Meta:
        constraints = [models.CheckConstraint(
            condition=models.Q(minimum_bid_increment__gt=0) | models.Q(minimum_bid_increment__isnull=True),
            name="auction_increment_positive",
        )]


class BidQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Accepted bids cannot be changed.')

    def delete(self):
        raise ValidationError('Accepted bids cannot be deleted.')


class Bid(models.Model):
    objects = BidQuerySet.as_manager()
    auction = models.ForeignKey(Auction, on_delete=models.PROTECT, related_name='bids')
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='auction_bids')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[validate_currency_code])
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='bid_amount_positive')]

    @property
    def bidder_label(self):
        identifier = salted_hmac('auction-bidder', f'{self.auction_id}:{self.buyer_id}').hexdigest()[:10]
        return f'Bidder {identifier}'

    def save(self, **kwargs):
        if not self._state.adding:
            raise ValidationError('Accepted bids cannot be changed.')
        self.full_clean()
        super().save(**kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Accepted bids cannot be deleted.')


class BidIneligibility(models.Model):
    bid = models.OneToOneField(Bid, on_delete=models.PROTECT, related_name='ineligibility')
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now, editable=False)


class AuctionOrder(models.Model):
    auction = models.OneToOneField(Auction, on_delete=models.PROTECT, related_name='order')
    winning_bid = models.OneToOneField(Bid, on_delete=models.PROTECT)
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='auction_sales')
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='auction_purchases')
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    payment_status = models.CharField(max_length=20, default='Pending')
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity=1), name='auction_order_one_item')]


class AuctionNotification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='auction_notifications')
    auction = models.ForeignKey(Auction, on_delete=models.PROTECT, related_name='notifications', null=True)
    order = models.ForeignKey(AuctionOrder, on_delete=models.PROTECT, related_name='notifications', null=True)
    message = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['recipient', 'order'], name='one_auction_notification_per_recipient'),
            models.UniqueConstraint(fields=['recipient', 'auction'], name='one_notification_per_auction_recipient'),
        ]


class ListingImage(models.Model):
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name="images",
    )
    # Content validation and metadata removal belong to the upload workflow.
    file = models.FileField(upload_to="listing_images/")
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]


class ListingStateChange(models.Model):
    listing = models.ForeignKey(
        Listing, on_delete=models.PROTECT, related_name="state_changes",
    )
    old_state = models.CharField(max_length=20, choices=Listing.State.choices)
    new_state = models.CharField(max_length=20, choices=Listing.State.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    # Only automatic changes use NULL; user deletion must preserve attribution.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="listing_state_changes",
    )

    class Meta:
        ordering = ["changed_at", "pk"]
