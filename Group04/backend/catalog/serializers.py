from decimal import Decimal, InvalidOperation

from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from .images import prepare_image
from .models import Category, CategoryAttribute, Listing, ListingImage
from .validators import validate_country_code, validate_currency_code
from .permissions import can_change_listing, listing_is_available
from .editing import validate_listing_edit


LISTING_FIELDS = [
    "title", "description", "price", "currency", "category", "condition",
    "quantity", "country", "postal_code", "attribute_values", "ends_at",
]


class CategorySerializer(serializers.ModelSerializer):
    is_leaf = serializers.BooleanField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "parent", "is_leaf"]


class CategoryAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryAttribute
        fields = [
            "id", "code", "name", "type", "required", "filterable",
            "min_value", "max_value", "options",
        ]


class ListingImageSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()

    class Meta:
        model = ListingImage
        fields = ["id", "file", "description", "position"]

    def get_file(self, image):
        url = reverse("catalog:image-file", args=[image.listing_id, image.pk])
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class ListingResultSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = ["id", "title", "primary_image", "price", "currency"]

    def get_primary_image(self, listing):
        image = next(iter(listing.images.all()), None)
        if image is None:
            return None
        return ListingImageSerializer(image, context=self.context).data["file"]


class ListingSerializer(serializers.ModelSerializer):
    details_locked = serializers.BooleanField(read_only=True)
    available_actions = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    seller_name = serializers.CharField(source="seller.public_display_name", read_only=True)
    condition_display = serializers.CharField(source="get_condition_display", read_only=True)
    images = ListingImageSerializer(many=True, read_only=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0.01"),
    )
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    attribute_values = serializers.DictField(required=False)

    class Meta:
        model = Listing
        fields = [
            "id", "seller", "state", *LISTING_FIELDS,
            "published_at", "created_at", "updated_at", "images",
            "available_actions", "is_available", "seller_name", "condition_display",
            "details_locked",
        ]
        read_only_fields = [
            "id", "seller", "state", "published_at", "created_at", "updated_at",
        ]

    def validate_country(self, value):
        value = value.upper()
        validate_country_code(value)
        return value

    def validate_currency(self, value):
        value = value.upper()
        validate_currency_code(value)
        return value

    def validate_category(self, category):
        if category is not None and not category.is_leaf:
            raise serializers.ValidationError("Select a category without subcategories.")
        return category

    def validate(self, attrs):
        forbidden = {
            name: "This field cannot be set here."
            for name in self.initial_data
            if name not in self.fields or self.fields[name].read_only
        }
        if forbidden:
            raise serializers.ValidationError(forbidden)
        if self.instance is not None:
            validate_listing_edit(self.instance, fields=attrs)

        category = attrs.get("category", getattr(self.instance, "category", None))
        values = attrs.get("attribute_values", getattr(self.instance, "attribute_values", {}))
        definitions = {a.code: a for a in category.attributes.all()} if category else {}
        errors = {}
        for code, value in values.items():
            attribute = definitions.get(code)
            if attribute is None:
                errors[code] = "This attribute does not belong to the selected category."
                continue
            # Drafts may leave required attributes empty.
            if value is None or value == "":
                continue
            if attribute.type == CategoryAttribute.Type.TEXT:
                if not isinstance(value, str):
                    errors[code] = "Enter text."
            elif attribute.type == CategoryAttribute.Type.CHOICE:
                if value not in attribute.options:
                    errors[code] = "Select one of the allowed choices."
            elif attribute.type == CategoryAttribute.Type.NUMBER:
                try:
                    if isinstance(value, bool):
                        raise InvalidOperation
                    number = Decimal(str(value))
                    if not number.is_finite():
                        raise InvalidOperation
                    if attribute.min_value is not None and number < attribute.min_value:
                        errors[code] = f"Must be at least {attribute.min_value}."
                    if attribute.max_value is not None and number > attribute.max_value:
                        errors[code] = f"Must be at most {attribute.max_value}."
                except (InvalidOperation, ValueError):
                    errors[code] = "Enter a valid number."
        if errors:
            raise serializers.ValidationError({"attribute_values": errors})
        if self.instance is not None and self.instance.state != Listing.State.DRAFT:
            data = {name: getattr(self.instance, name) for name in LISTING_FIELDS}
            data.update(attrs)
            data["category"] = data["category"].pk if data["category"] is not None else None
            complete = ListingPublicationSerializer(data=data, context={
                "listing": self.instance, "allow_zero_stock": True,
                "publication_time": self.instance.published_at or self.instance.created_at,
            })
            complete.is_valid(raise_exception=True)
        return attrs

    def create(self, validated_data):
        from .services import create_listing_draft

        return create_listing_draft(self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        from .services import update_listing_details

        return update_listing_details(instance.pk, validated_data)

    def get_is_available(self, listing):
        return listing_is_available(listing)

    def get_available_actions(self, listing):
        request = self.context.get("request")
        if request is None:
            return []
        actions = []
        if listing.state != Listing.State.REMOVED:
            actions.append("edit")
        if listing.state == Listing.State.DRAFT:
            actions.append("publish")
        elif listing.state == Listing.State.ACTIVE:
            actions.extend(["pause", "end"])
        elif listing.state == Listing.State.PAUSED:
            actions.append("end")
            if listing.quantity and (listing.ends_at is None or listing.ends_at > timezone.now()):
                actions.append("resume")
        if listing.state != Listing.State.REMOVED:
            actions.append("remove")
        return [action for action in actions if can_change_listing(request.user, listing, action)]


class ListingPublicationSerializer(ListingSerializer):
    """Validate all saved details; draft editing uses the relaxed parent serializer."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        errors = {}
        for field in ("title", "description", "category", "condition", "currency", "country", "postal_code"):
            if not attrs.get(field):
                errors[field] = "This field is required before publication."
        if attrs.get("title") and len(attrs["title"]) < 10:
            errors["title"] = "Use at least 10 characters."
        if attrs.get("description") and len(attrs["description"]) < 20:
            errors["description"] = "Use at least 20 characters."
        if attrs.get("price") is None:
            errors["price"] = "A positive price is required before publication."
        minimum_stock = 0 if self.context.get("allow_zero_stock") else 1
        if attrs.get("quantity") is None or attrs["quantity"] < minimum_stock:
            errors["quantity"] = "Publishing requires at least one item."

        publication_time = self.context.get("publication_time") or timezone.now()
        if attrs.get("ends_at") is not None and attrs["ends_at"] <= publication_time:
            errors["ends_at"] = "The end time must be later than publication."

        category = attrs.get("category")
        if category is not None:
            values = attrs.get("attribute_values", {})
            missing = {}
            for attribute in category.attributes.filter(required=True):
                value = values.get(attribute.code)
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing[attribute.code] = "This attribute is required before publication."
            if missing:
                errors["attribute_values"] = missing

        if not 1 <= self.context["listing"].images.count() <= 5:
            errors["images"] = "Publishing requires between one and five images."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class ImageUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_file(self, upload):
        return prepare_image(upload)


class ImageDescriptionSerializer(serializers.Serializer):
    description = serializers.CharField(allow_blank=True)

    def validate(self, attrs):
        if set(self.initial_data) != {"description"}:
            raise serializers.ValidationError("Only the image description can be changed here.")
        return attrs


class ImageOrderSerializer(serializers.Serializer):
    image_ids = serializers.ListField(child=serializers.IntegerField(min_value=1))

    def validate_image_ids(self, ids):
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each image must appear exactly once.")
        return ids
