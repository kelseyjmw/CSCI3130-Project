from django.contrib.auth import get_user_model

from catalog.models import Category, Listing
from tests.catalog.helpers import CatalogAPITestCase


class TextSearchTests(CatalogAPITestCase):
    url = "/api/catalog/listings/"

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(None)
        self.category = Category.objects.create(name="Search items")

    def make_listing(self, **overrides):
        fields = {
            "seller": self.seller, "state": "active", "quantity": 1,
            "title": "Travel kit", "description": "A practical item in working condition.",
            "category": self.category, "price": "400.00", "currency": "CAD", "condition": "used_good",
        }
        return Listing.objects.create(**(fields | overrides))

    def matching_ids(self, q=None, **filters):
        if q is not None:
            filters["q"] = q
        response = self.client.get(self.url, filters)
        self.assertEqual(response.status_code, 200, response.data)
        return {row["id"] for row in response.data["results"]}

    def test_guests_and_logged_in_users_can_match_either_field(self):
        title = self.make_listing(title="Digital camera")
        description = self.make_listing(description="Includes a camera and a carrying case.")
        both = self.make_listing(title="Another camera", description="A camera in good condition.")
        self.make_listing(title="Office chair")
        buyer = get_user_model().objects.create_user(email="search-buyer@example.com", email_verified=True)
        for user in (None, buyer):
            with self.subTest(user=user):
                self.client.force_authenticate(user)
                self.assertEqual(self.matching_ids("camera"), {title.pk, description.pk, both.pk})

    def test_search_is_case_insensitive_in_both_fields(self):
        title = self.make_listing(title="Working LAPTOP")
        description = self.make_listing(description="Includes a laptop and its charger.")
        for query in ("Laptop", "laptop", "LAPTOP"):
            with self.subTest(query=query):
                self.assertEqual(self.matching_ids(query), {title.pk, description.pk})

    def test_every_word_is_required_and_words_can_be_in_different_fields(self):
        split_fields = self.make_listing(title="Digital camera", description="Includes a carrying case.")
        description_only = self.make_listing(description="Camera with its protective case.")
        self.make_listing(title="Digital camera")
        self.make_listing(description="A carrying case for accessories.")
        for query in ("camera case", " CASE camera ", "camera\t\ncase", "camera camera case"):
            with self.subTest(query=query):
                self.assertEqual(self.matching_ids(query), {split_fields.pk, description_only.pk})

    def test_empty_query_uses_only_the_selected_filters(self):
        match = self.make_listing()
        for overrides in (
            {"currency": "USD"}, {"price": "600.00"}, {"condition": "new"},
            {"category": Category.objects.create(name="Other search items")}, {"state": "draft"},
        ):
            self.make_listing(**overrides)
        for query in (None, "", "   ", "\t\n"):
            with self.subTest(query=query):
                self.assertEqual(self.matching_ids(
                    query, category=self.category.pk, currency="CAD", max_price="500", condition="used_good",
                ), {match.pk})

    def test_text_search_and_filters_share_the_paginated_count(self):
        fields = {"title": "Digital camera", "description": "Includes a carrying case."}
        first = self.make_listing(**fields)
        second = self.make_listing(**fields)
        self.make_listing(**fields, currency="USD")
        self.make_listing(**fields, price="600.00")
        self.make_listing(**fields, state="paused")
        response = self.client.get(self.url, {
            "q": "camera case", "currency": "CAD", "max_price": "500", "page_size": 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["total_pages"], 2)
        next_page = self.client.get(response.data["next"])
        self.assertEqual(next_page.status_code, 200)
        self.assertEqual(next_page.data["count"], 2)
        rows = response.data["results"] + next_page.data["results"]
        self.assertEqual({row["id"] for row in rows}, {first.pk, second.pk})

    def test_matching_is_by_substring_and_sql_wildcards_are_literal(self):
        match = self.make_listing(title="Camera bag 100% ready")
        self.make_listing(title="Camera bag 1000 ready")
        self.assertEqual(self.matching_ids("cam 100%"), {match.pk})

    def test_overlong_queries_return_a_clear_error(self):
        response = self.client.get(self.url, {"q": "x" * 201})
        self.assertEqual(response.status_code, 400)
        self.assertIn("q", response.data)
