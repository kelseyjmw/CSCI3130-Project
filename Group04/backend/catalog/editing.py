from rest_framework.exceptions import ValidationError


def validate_listing_edit(listing, fields=None, images=False):
    if not listing.details_locked:
        return
    if images or set(fields or {}) != {"quantity"}:
        raise ValidationError("After the first purchase, only increasing stock is allowed. Listing details and images are locked.")
    quantity = fields["quantity"]
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= (listing.quantity or 0):
        raise ValidationError({"quantity": "Stock must be greater than the current quantity."})
