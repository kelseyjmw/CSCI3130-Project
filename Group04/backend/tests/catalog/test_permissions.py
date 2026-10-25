from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView
from catalog.models import Listing
from catalog.permissions import CanChangeListing, CanCreateListing, can_change_listing, can_create_listing
from security.models import Role
from security.permissions import grant_seller, user_has_permission


class ListingPermissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.seller = User.objects.create_user(email="owner@example.com", email_verified=True)
        self.other = User.objects.create_user(email="other@example.com", email_verified=True)
        self.moderator = User.objects.create_user(email="mod@example.com", email_verified=True)
        self.admin = User.objects.create_user(email="admin@example.com", email_verified=True)
        grant_seller(self.seller)
        grant_seller(self.other)
        Role.objects.get(name="Moderator").users.add(self.moderator)
        Role.objects.get(name="Administrator").users.add(self.admin)
        self.listing = Listing.objects.create(seller=self.seller)

    def test_approval_grants_creation_using_existing_seller_role(self):
        user = get_user_model().objects.create_user(email="approved@example.com", email_verified=True)
        self.assertFalse(can_create_listing(user))
        grant_seller(user)
        self.assertTrue(can_create_listing(user))
        self.assertTrue(user_has_permission(user, "listings.create"))

    def test_admin_without_seller_role_cannot_create_or_publish(self):
        self.assertFalse(can_create_listing(self.admin))
        listing = Listing(seller=self.admin)
        self.assertFalse(can_change_listing(self.admin, listing, "publish"))

    def test_anonymous_unverified_and_inactive_users_are_denied(self):
        self.assertFalse(can_create_listing(AnonymousUser()))
        self.assertFalse(can_change_listing(AnonymousUser(), self.listing))
        for field in ("email_verified", "is_active"):
            with self.subTest(field=field):
                setattr(self.seller, field, False)
                self.assertFalse(can_create_listing(self.seller))
                self.assertFalse(can_change_listing(self.seller, self.listing, "publish"))
                self.assertFalse(can_change_listing(self.seller, self.listing))
                setattr(self.seller, field, True)

    def test_seller_cannot_change_another_listing_or_remove_own_listing(self):
        for action in ("edit", "publish", "resume", "pause", "end", "remove"):
            with self.subTest(action=action):
                self.assertFalse(can_change_listing(self.other, self.listing, action))
        self.assertFalse(can_change_listing(self.seller, self.listing, "remove"))

    def test_owner_can_manage_listing_but_unknown_actions_are_denied(self):
        for action in ("edit", "publish", "resume", "pause", "end"):
            with self.subTest(action=action):
                self.assertTrue(can_change_listing(self.seller, self.listing, action))
        self.assertFalse(can_change_listing(self.seller, self.listing, "unknown"))

    def test_moderation_uses_existing_remove_permission(self):
        for user in (self.moderator, self.admin):
            self.assertTrue(can_change_listing(user, self.listing, "remove"))
            self.assertTrue(can_change_listing(user, self.listing, "edit"))
            self.assertFalse(can_change_listing(user, self.listing, "publish"))
        self.moderator.email_verified = False
        self.assertFalse(can_change_listing(self.moderator, self.listing, "remove"))

    def test_suspension_blocks_publication_and_resuming_but_keeps_existing_policy(self):
        self.seller.account_state = "Suspended"
        self.assertTrue(can_create_listing(self.seller))
        self.assertTrue(can_change_listing(self.seller, self.listing, "pause"))
        self.assertTrue(can_change_listing(self.seller, self.listing, "end"))
        self.assertFalse(can_change_listing(self.seller, self.listing, "publish"))
        self.assertFalse(can_change_listing(self.seller, self.listing, "resume"))

    def test_role_revocation_removes_owner_permissions(self):
        Role.objects.get(name="Seller").users.remove(self.seller)
        self.assertFalse(can_create_listing(self.seller))
        self.assertFalse(can_change_listing(self.seller, self.listing))

    def test_object_permission_rejects_identifier_swap_through_drf(self):
        class EditPermissionProbe(APIView):
            permission_classes = [IsAuthenticated, CanChangeListing]

            def patch(view, request, pk):
                listing = Listing.objects.get(pk=pk)
                view.check_object_permissions(request, listing)
                return Response({"ok": True})

        for user, expected in ((self.seller, 200), (self.other, 403), (self.moderator, 200)):
            request = APIRequestFactory().patch("/", {})
            force_authenticate(request, user=user)
            response = EditPermissionProbe.as_view()(request, pk=self.listing.pk)
            self.assertEqual(response.status_code, expected)

    def test_creation_permission_class_uses_same_rules(self):
        request = APIRequestFactory().post("/", {})
        request.user = self.seller
        self.assertTrue(CanCreateListing().has_permission(request, None))
        request.user = self.moderator
        self.assertFalse(CanCreateListing().has_permission(request, None))
