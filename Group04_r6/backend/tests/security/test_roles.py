from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from security.models import Permission, Role


User = get_user_model()


class LastAdminTests(TestCase):
    def test_cannot_remove_last_admin(self):
        role, _ = Role.objects.get_or_create(name="Administrator")
        admin = User.objects.create_user("admin1@test.com", "pass", is_staff=True)
        role.users.add(admin)
        with self.assertRaises(ValidationError):
            role.users.remove(admin)

    def test_cannot_deactivate_last_admin(self):
        role, _ = Role.objects.get_or_create(name="Administrator")
        admin = User.objects.create_user("admin1@test.com", "pass", is_staff=True)
        role.users.add(admin)
        admin.is_active = False
        with self.assertRaises(ValidationError):
            admin.save()

    def test_can_remove_admin_when_two_exist(self):
        role, _ = Role.objects.get_or_create(name="Administrator")
        admin1 = User.objects.create_user("admin1@test.com", "pass", is_staff=True)
        admin2 = User.objects.create_user("admin2@test.com", "pass", is_staff=True)
        role.users.add(admin1, admin2)
        role.users.remove(admin2)
        self.assertFalse(admin2.roles.filter(name="Administrator").exists())
        self.assertTrue(admin1.roles.filter(name="Administrator").exists())


class RoleAdminTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        perm, _ = Permission.objects.get_or_create(code="accounts.change_roles")
        self.admin_role, _ = Role.objects.get_or_create(name="Administrator")
        self.admin_role.permissions.add(perm)
        buyer_role, _ = Role.objects.get_or_create(name="Buyer")
        self.admin = User.objects.create_user(
            "admin1@test.com", "pass", email_verified=True
        )
        self.buyer = User.objects.create_user(
            "buyer1@test.com", "pass", email_verified=True
        )
        self.admin_role.users.add(self.admin)
        buyer_role.users.add(self.buyer)

    def test_me_returns_roles(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/accounts/me/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Administrator", res.data["roles"])

    def test_buyer_cannot_list_users(self):
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get("/api/security/users/").status_code, 403)

    def test_admin_can_set_roles(self):
        self.client.force_authenticate(self.admin)
        res = self.client.put(
            f"/api/security/users/{self.buyer.id}/",
            {"roles": ["Buyer", "Moderator"]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(sorted(res.data["roles"]), ["Buyer", "Moderator"])

    def test_cannot_remove_last_admin_via_api(self):
        self.client.force_authenticate(self.admin)
        res = self.client.put(
            f"/api/security/users/{self.admin.id}/",
            {"roles": ["Buyer"]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_unverified_admin_denied(self):
        self.admin.email_verified = False
        self.admin.save()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/security/users/").status_code, 403)
