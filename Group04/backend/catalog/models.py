from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

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
    def delete(self):
        raise ValidationError("Listings must be removed by changing their state, not deleted.")


class Listing(models.Model):
    objects = ListingQuerySet.as_manager()

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
        return self.details_locked_at is not None

    def delete(self, *args, **kwargs):
        raise ValidationError("Listings must be removed by changing their state, not deleted.")


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
