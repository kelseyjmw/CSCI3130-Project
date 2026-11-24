from rest_framework.exceptions import ValidationError


def validate_listing_edit(listing, fields=None, images=False):
    if fields and "listing_type" in fields and fields["listing_type"] != listing.listing_type and (
        listing.published_at is not None or listing.state != "draft"
    ):
        raise ValidationError({"listing_type": "The sale type cannot change after publication."})
    listing.sale_behavior.validate_edit(fields, images)
    if not listing.details_locked:
        return
    if images or set(fields or {}) != {"quantity"}:
        raise ValidationError("After the first purchase, only increasing stock is allowed. Listing details and images are locked.")
    quantity = fields["quantity"]
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= (listing.quantity or 0):
        raise ValidationError({"quantity": "Stock must be greater than the current quantity."})
