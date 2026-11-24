import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient


User = get_user_model()


class BootstrapTests(TestCase):
    def test_register_assigns_buyer_only(self):
        res = APIClient().post(
            "/api/accounts/register/",
            {
                "email": "newbuyer@test.com",
                "password": "TestPass123!",
                "roles": ["Administrator"],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="newbuyer@test.com")
        self.assertEqual(list(user.roles.values_list("name", flat=True)), ["Buyer"])

    @patch.dict(
        os.environ,
        {"ADMIN_EMAIL": "first@test.com", "ADMIN_PASSWORD": "AdminPass123!"},
    )
    def test_create_admin_twice_still_one(self):
        call_command("create_admin")
        call_command("create_admin")
        self.assertEqual(
            User.objects.filter(roles__name="Administrator").distinct().count(),
            1,
        )
