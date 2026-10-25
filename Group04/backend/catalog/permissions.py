from rest_framework.permissions import BasePermission
from django.utils import timezone

from security.permissions import user_has_permission


def seller_can_sell(seller):
    return (
        seller.is_active and seller.email_verified and seller.account_state == "Active"
        and seller.roles.filter(name="Seller").exists()
    )


def listing_is_available(listing):
    return (
        listing.state == "active" and listing.quantity is not None and listing.quantity > 0
        and (listing.ends_at is None or listing.ends_at > timezone.now())
        and seller_can_sell(listing.seller)
    )


def can_view_listing(user, listing):
    if user.is_authenticated and user.is_active and listing.seller_id == user.pk:
        return True
    if user_has_permission(user, "listings.remove"):
        return True
    return listing.state in ("active", "sold_out", "ended") and seller_can_sell(listing.seller)


def can_create_listing(user):
    # Approval grants Seller through security.permissions.grant_seller.
    return (
        user_has_permission(user, "listings.create")
        and user.roles.filter(name="Seller").exists()
    )


def can_change_listing(user, listing, action="edit"):
    if action == "remove":
        return user_has_permission(user, "listings.remove")
    if action == "edit" and user_has_permission(user, "listings.remove"):
        return True
    if listing.seller_id != user.pk:
        return False
    if action in ("publish", "resume"):
        return (
            can_create_listing(user)
            and user.account_state == "Active"
            and user_has_permission(user, "listings.publish")
        )
    if action in ("edit", "pause", "end"):
        return (
            user_has_permission(user, "listings.edit")
            and user.roles.filter(name="Seller").exists()
        )
    return False


class CanCreateListing(BasePermission):
    message = "An approved seller with a verified email and an active login is required."

    def has_permission(self, request, view):
        return can_create_listing(request.user)


class CanChangeListing(BasePermission):
    message = "You do not have permission to perform this action on this listing."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_active
            and request.user.email_verified
        )

    def has_object_permission(self, request, view, obj):
        return can_change_listing(request.user, obj, getattr(view, "listing_action", "edit"))
