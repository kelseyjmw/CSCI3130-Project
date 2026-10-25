from rest_framework.permissions import BasePermission

from .models import Role

PUBLIC = {"listings.view"}
SUSPENDED_BLOCKED = {"items.buy", "listings.publish", "messages.send"}


def requires_active_account(user, code):
    if code not in SUSPENDED_BLOCKED:
        return True
    return getattr(user, "account_state", "Active") != "Suspended"


def user_has_permission(user, code):
    if code in PUBLIC:
        return True
    if not user.is_authenticated or not user.is_active:
        return False
    if getattr(user, "email_verified", None) is False:
        return False
    codes = Role.objects.filter(users=user).values_list(
        "permissions__code", flat=True
    )
    if code not in codes:
        return False
    return requires_active_account(user, code)


def assign_buyer(user):
    role, _ = Role.objects.get_or_create(name="Buyer")
    role.users.add(user)


def grant_seller(user):
    role, _ = Role.objects.get_or_create(name="Seller")
    role.users.add(user)


class HasPermission(BasePermission):
    def has_permission(self, request, view):
        needed = getattr(view, "required_permission", None)
        if not needed:
            return True
        return user_has_permission(request.user, needed)


    def test_unverified_admin_denied(self):
        admin_role, _ = Role.objects.get_or_create(name="Administrator")
        admin_role.permissions.add(Permission.objects.get(code="items.buy"))
        admin = User.objects.create_user(
            "admin_unverified@test.com", "pass", is_staff=True, email_verified=False
        )
        admin_role.users.add(admin)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/protected/").status_code, 403)
