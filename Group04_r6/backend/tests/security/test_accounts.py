from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.test import APIClient
from accounts.models import AuditLog
from security.models import Permission, Role
from security.permissions import user_has_permission


User = get_user_model()


class AccountStateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        perm, _ = Permission.objects.get_or_create(code="accounts.suspend")
        buy, _ = Permission.objects.get_or_create(code="items.buy")
        self.admin_role, _ = Role.objects.get_or_create(name="Administrator")
        self.mod_role, _ = Role.objects.get_or_create(name="Moderator")
        buyer_role, _ = Role.objects.get_or_create(name="Buyer")
        self.admin_role.permissions.add(perm, buy)
        self.mod_role.permissions.add(perm, buy)
        buyer_role.permissions.add(buy)
        self.admin = User.objects.create_user(
            "admin1@test.com", "pass", email_verified=True
        )
        self.mod = User.objects.create_user(
            "mod1@test.com", "pass", email_verified=True
        )
        self.buyer = User.objects.create_user(
            "buyer1@test.com", "pass", email_verified=True
        )
        self.admin_role.users.add(self.admin)
        self.mod_role.users.add(self.mod)
        buyer_role.users.add(self.buyer)

    def test_new_user_is_active(self):
        self.assertEqual(self.buyer.account_state, "Active")

    def test_new_account_active_but_unverified_restricted(self):
        user = User.objects.create_user(
            "new@test.com", "pass", email_verified=False
        )
        self.assertEqual(user.account_state, "Active")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/protected/").status_code, 403)

    def test_me_returns_account_state(self):
        self.client.force_authenticate(self.buyer)
        res = self.client.get("/api/accounts/me/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["account_state"], "Active")

    def test_suspended_buyer_denied_buy(self):
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "spam"
        self.buyer.save()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get("/api/protected/").status_code, 403)

    def test_suspended_can_login(self):
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "spam"
        self.buyer.save()
        res = Client().post(
            "/api/accounts/login/",
            data='{"email":"buyer1@test.com","password":"pass"}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

    def test_buyer_cannot_suspend(self):
        self.client.force_authenticate(self.buyer)
        res = self.client.put(
            f"/api/security/account-state/{self.mod.id}/",
            {"account_state": "Suspended", "reason": "no"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_mod_can_suspend_with_reason(self):
        self.client.force_authenticate(self.mod)
        res = self.client.put(
            f"/api/security/account-state/{self.buyer.id}/",
            {"account_state": "Suspended", "reason": "spam listings"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["account_state"], "Suspended")
        self.assertEqual(res.data["suspension_reason"], "spam listings")

    def test_reason_required(self):
        self.client.force_authenticate(self.mod)
        res = self.client.put(
            f"/api/security/account-state/{self.buyer.id}/",
            {"account_state": "Suspended", "reason": "  "},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_cannot_suspend_last_admin(self):
        self.client.force_authenticate(self.mod)
        res = self.client.put(
            f"/api/security/account-state/{self.admin.id}/",
            {"account_state": "Suspended", "reason": "test"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_suspend_writes_audit(self):
        self.client.force_authenticate(self.mod)
        self.client.put(
            f"/api/security/account-state/{self.buyer.id}/",
            {"account_state": "Suspended", "reason": "spam listings"},
            format="json",
        )
        row = AuditLog.objects.get(action="account_state", target=self.buyer.id)
        self.assertEqual(row.actor, self.mod.id)
        self.assertEqual(row.result, "success")
        self.assertEqual(row.reason, "spam listings")

    def test_reactivate_writes_audit(self):
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "spam"
        self.buyer.save()
        self.client.force_authenticate(self.mod)
        res = self.client.put(
            f"/api/security/account-state/{self.buyer.id}/",
            {"account_state": "Active", "reason": "appeal accepted"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["account_state"], "Active")
        row = AuditLog.objects.get(action="account_state", target=self.buyer.id)
        self.assertEqual(row.reason, "appeal accepted")

    def test_no_auto_expiry(self):
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "spam"
        self.buyer.save()
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.account_state, "Suspended")

    def test_suspended_seller_cannot_publish(self):
        publish, _ = Permission.objects.get_or_create(code="listings.publish")
        seller_role, _ = Role.objects.get_or_create(name="Seller")
        seller_role.permissions.add(publish)
        seller = User.objects.create_user(
            "seller1@test.com", "pass", email_verified=True
        )
        seller_role.users.add(seller)
        seller.account_state = "Suspended"
        seller.suspension_reason = "spam"
        seller.save()
        self.assertFalse(user_has_permission(seller, "listings.publish"))

    def test_suspended_admin_denied_buy(self):
        extra = User.objects.create_user(
            "admin2@test.com", "pass", email_verified=True
        )
        self.admin_role.users.add(extra)
        self.admin.account_state = "Suspended"
        self.admin.suspension_reason = "test"
        self.admin.save()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/protected/").status_code, 403)

    def test_suspended_multi_role_denied(self):
        publish, _ = Permission.objects.get_or_create(code="listings.publish")
        seller_role, _ = Role.objects.get_or_create(name="Seller")
        seller_role.permissions.add(publish)
        seller_role.users.add(self.buyer)
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "spam"
        self.buyer.save()
        self.assertFalse(user_has_permission(self.buyer, "items.buy"))
        self.assertFalse(user_has_permission(self.buyer, "listings.publish"))

    def test_read_only_still_works(self):
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "spam"
        self.buyer.save()
        self.assertTrue(user_has_permission(self.buyer, "listings.view"))

    def test_owner_sees_suspension_reason(self):
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "not used"
        self.buyer.save()
        self.client.force_authenticate(self.buyer)
        res = self.client.get("/api/accounts/me/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["suspension_reason"], "not used")

    def test_other_users_do_not_see_reason(self):
        self.buyer.account_state = "Suspended"
        self.buyer.suspension_reason = "not used"
        self.buyer.save()
        self.client.force_authenticate(self.mod)
        res = self.client.get(f"/api/accounts/profiles/{self.buyer.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("suspension_reason", res.data)
