from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from security.models import Permission, Role
from security.permissions import user_has_permission


User = get_user_model()


class PermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        perm, _ = Permission.objects.get_or_create(code="items.buy")
        role, _ = Role.objects.get_or_create(name="Buyer")
        role.permissions.add(perm)
        self.buyer = User.objects.create_user(
            "buyer1@test.com", "pass", email_verified=True
        )
        self.other = User.objects.create_user(
            "other@test.com", "pass", email_verified=True
        )
        role.users.add(self.buyer)

    def test_buyer_allowed(self):
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get("/api/protected/").status_code, 200)

    def test_no_role_denied(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/protected/").status_code, 403)

    def test_unverified_buyer_denied(self):
        self.buyer.email_verified = False
        self.buyer.save()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get("/api/protected/").status_code, 403)

    def test_two_roles_grant_both_permissions(self):
        publish, _ = Permission.objects.get_or_create(code="listings.publish")
        seller, _ = Role.objects.get_or_create(name="Seller")
        seller.permissions.add(publish)
        seller.users.add(self.buyer)
        self.assertTrue(user_has_permission(self.buyer, "items.buy"))
        self.assertTrue(user_has_permission(self.buyer, "listings.publish"))

    def test_removing_permission_from_role_denies_access(self):
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get("/api/protected/").status_code, 200)
        Role.objects.get(name="Buyer").permissions.clear()
        self.assertEqual(self.client.get("/api/protected/").status_code, 403)
