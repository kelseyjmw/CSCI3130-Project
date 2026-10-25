from django.db.models import DecimalField, Q, TextField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from rest_framework import serializers

from .models import Category, CategoryAttribute, Listing
from .validators import validate_currency_code


class ListingFilterSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=200)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False)
    currency = serializers.CharField(default="CAD", max_length=3)
    min_price = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0, required=False)
    max_price = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0, required=False)
    condition = serializers.ChoiceField(choices=Listing.Condition.choices, required=False)
    ordering = serializers.ChoiceField(choices=["newest", "price", "-price"], default="newest")
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)

    def validate_currency(self, value):
        value = value.upper()
        validate_currency_code(value)
        return value

    def validate_category(self, category):
        if not category.is_leaf:
            raise serializers.ValidationError("Select a category without subcategories.")
        return category

    def validate(self, attrs):
        errors = {}
        if "min_price" in attrs and "max_price" in attrs and attrs["min_price"] > attrs["max_price"]:
            errors["max_price"] = "The maximum price must be at least the minimum price."

        category = attrs.get("category")
        definitions = {a.code: a for a in category.attributes.filter(filterable=True)} if category else {}
        attributes = []
        for name, value in self.initial_data.items():
            if name in self.fields:
                continue
            attribute = definitions.get(name.removeprefix("attr.")) if name.startswith("attr.") else None
            if attribute is None:
                errors[name] = "Select a searchable attribute belonging to the selected category." if name.startswith("attr.") else "Unknown filter."
                continue
            if attribute.type == CategoryAttribute.Type.NUMBER:
                field = serializers.DecimalField(
                    max_digits=15, decimal_places=4,
                    min_value=attribute.min_value, max_value=attribute.max_value,
                )
            elif attribute.type == CategoryAttribute.Type.CHOICE:
                field = serializers.ChoiceField(choices=attribute.options)
            else:
                field = serializers.CharField(max_length=200)
            try:
                attributes.append((attribute, field.run_validation(value)))
            except serializers.ValidationError as exc:
                errors[name] = exc.detail
        if errors:
            raise serializers.ValidationError(errors)
        attrs["attributes"] = attributes
        return attrs


def filter_listings(queryset, params):
    repeated = {name: "Provide only one value per filter." for name in params if len(params.getlist(name)) != 1}
    if repeated:
        raise serializers.ValidationError(repeated)
    serializer = ListingFilterSerializer(data=params.dict())
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    queryset = queryset.filter(currency=filters["currency"])
    for term in filters.get("q", "").split():
        queryset = queryset.filter(Q(title__icontains=term) | Q(description__icontains=term))
    if "category" in filters:
        queryset = queryset.filter(category=filters["category"])
    if "condition" in filters:
        queryset = queryset.filter(condition=filters["condition"])
    if "min_price" in filters:
        queryset = queryset.filter(price__gte=filters["min_price"])
    if "max_price" in filters:
        queryset = queryset.filter(price__lte=filters["max_price"])
    for index, (attribute, value) in enumerate(filters["attributes"]):
        key = f"attribute_values__{attribute.code}"
        # Draft values may be empty or null; neither represents a numeric zero.
        queryset = queryset.filter(**{f"{key}__isnull": False}).exclude(**{key: None}).exclude(**{key: ""})
        alias = f"filter_attribute_{index}"
        expression = KeyTextTransform(attribute.code, "attribute_values")
        output_field = DecimalField(max_digits=15, decimal_places=4) if attribute.type == CategoryAttribute.Type.NUMBER else TextField()
        expression = Cast(expression, output_field)
        queryset = queryset.alias(**{alias: expression})
        lookup = f"{alias}__icontains" if attribute.type == CategoryAttribute.Type.TEXT else alias
        queryset = queryset.filter(**{lookup: value})
    ordering = {
        "newest": ("-published_at", "-pk"),
        "price": ("price", "pk"),
        "-price": ("-price", "pk"),
    }
    return queryset.order_by(*ordering[filters["ordering"]])
