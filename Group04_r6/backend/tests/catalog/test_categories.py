from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from catalog.models import Category, CategoryAttribute


class CatalogSeedAndReadTests(TestCase):
    def setUp(self):
        call_command("seed_catalog", stdout=StringIO())
        self.client = APIClient(enforce_csrf_checks=True)

    def test_seed_can_be_repeated_and_updates_definitions(self):
        ids = list(Category.objects.order_by("pk").values_list("pk", flat=True))
        CategoryAttribute.objects.filter(code="laptop_memory_gb").update(max_value=1)
        call_command("seed_catalog", stdout=StringIO())
        self.assertEqual(Category.objects.count(), 7)
        self.assertEqual(CategoryAttribute.objects.count(), 8)
        self.assertEqual(list(Category.objects.order_by("pk").values_list("pk", flat=True)), ids)
        self.assertEqual(CategoryAttribute.objects.get(code="laptop_memory_gb").max_value, 1024)

    def test_public_categories_include_parent_and_leaf_information(self):
        response = self.client.get("/api/catalog/categories/")
        self.assertEqual(response.status_code, 200)
        rows = {row["name"]: row for row in response.data}
        self.assertIsNone(rows["Electronics"]["parent"])
        self.assertFalse(rows["Computers"]["is_leaf"])
        self.assertTrue(rows["Laptops"]["is_leaf"])
        self.assertEqual(rows["Laptops"]["parent"], rows["Computers"]["id"])

    def test_attributes_are_category_specific_and_include_validation_rules(self):
        laptops = Category.objects.get(name="Laptops")
        response = self.client.get(f"/api/catalog/categories/{laptops.pk}/attributes/")
        self.assertEqual(response.status_code, 200)
        rows = {row["code"]: row for row in response.data}
        self.assertEqual(set(rows), {"laptop_brand", "laptop_memory_gb", "laptop_storage_gb"})
        self.assertEqual(rows["laptop_memory_gb"]["type"], "number")
        self.assertEqual(float(rows["laptop_memory_gb"]["min_value"]), 0)
        self.assertEqual(float(rows["laptop_memory_gb"]["max_value"]), 1024)
        self.assertTrue(rows["laptop_memory_gb"]["required"])
        self.assertTrue(rows["laptop_memory_gb"]["filterable"])
        chairs = Category.objects.get(name="Chairs")
        response = self.client.get(f"/api/catalog/categories/{chairs.pk}/attributes/")
        material = next(row for row in response.data if row["code"] == "chair_material")
        self.assertIn("wood", material["options"])

    def test_unknown_category_is_404_and_parent_has_no_inherited_attributes(self):
        self.assertEqual(self.client.get("/api/catalog/categories/999999/attributes/").status_code, 404)
        computers = Category.objects.get(name="Computers")
        self.assertEqual(self.client.get(f"/api/catalog/categories/{computers.pk}/attributes/").data, [])

    def test_read_endpoints_work_with_existing_django_session(self):
        user = get_user_model().objects.create_user(email="reader@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/api/catalog/categories/").status_code, 200)

    def test_category_endpoints_are_read_only(self):
        self.assertEqual(self.client.post("/api/catalog/categories/", {}, format="json").status_code, 405)
        category = Category.objects.first()
        url = f"/api/catalog/categories/{category.pk}/attributes/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 405)
