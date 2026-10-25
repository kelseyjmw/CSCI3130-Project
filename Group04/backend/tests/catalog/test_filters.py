from datetime import timedelta

from django.utils import timezone

from catalog.models import Category, CategoryAttribute, Listing
from tests.catalog.helpers import CatalogAPITestCase


class CatalogFilterTests(CatalogAPITestCase):
    url = "/api/catalog/listings/"

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(None)
        self.parent = Category.objects.create(name="Computers")
        self.laptops = Category.objects.create(name="Laptops", parent=self.parent)
        self.chairs = Category.objects.create(name="Chairs")
        CategoryAttribute.objects.create(
            category=self.laptops, name="Brand", code="brand", type="text", filterable=True,
        )
        CategoryAttribute.objects.create(
            category=self.laptops, name="Memory", code="memory", type="number",
            filterable=True, min_value=0, max_value=1024,
        )
        CategoryAttribute.objects.create(
            category=self.laptops, name="Finish", code="finish", type="choice",
            filterable=True, options=["silver", "black"],
        )
        CategoryAttribute.objects.create(
            category=self.laptops, name="Serial", code="serial", type="text", filterable=False,
        )
        CategoryAttribute.objects.create(
            category=self.chairs, name="Material", code="material", type="choice",
            filterable=True, options=["wood", "metal"],
        )

    def make_listing(self, **overrides):
        fields = {
            "seller": self.seller, "state": "active", "title": "Example laptop",
            "description": "A working laptop with complete details.", "category": self.laptops,
            "price": "500.00", "currency": "CAD", "quantity": 1, "condition": "used_good",
            "attribute_values": {"brand": "Example Brand", "memory": 16, "finish": "silver"},
        }
        fields.update(overrides)
        return Listing.objects.create(**fields)

    def ids(self, **filters):
        response = self.client.get(self.url, filters)
        self.assertEqual(response.status_code, 200, response.data)
        return {row["id"] for row in response.data["results"]}

    def test_default_currency_and_changing_currency(self):
        cad = self.make_listing()
        usd = self.make_listing(currency="USD")
        self.assertEqual(self.ids(), {cad.pk})
        self.assertEqual(self.ids(currency="usd"), {usd.pk})

    def test_text_and_all_selected_filters_are_combined(self):
        match = self.make_listing()
        for override in (
            {"title": "Office computer", "description": "A complete office computer for sale."},
            {"category": self.chairs}, {"currency": "USD"},
            {"condition": "new"}, {"price": "500.01"}, {"price": "399.99"},
            {"attribute_values": {"brand": "Other", "memory": 16}},
            {"attribute_values": {"brand": "Example Brand", "memory": 8}},
        ):
            self.make_listing(**override)
        self.assertEqual(self.ids(
            q=" LAPTOP ", category=self.laptops.pk, currency="CAD", condition="used_good",
            min_price="400", max_price="500", **{"attr.brand": "example", "attr.memory": "16"},
        ), {match.pk})

    def test_price_boundaries_are_inclusive_and_zero_is_valid(self):
        lower = self.make_listing(price="100.00")
        upper = self.make_listing(price="500.00")
        self.make_listing(price="99.99")
        self.make_listing(price="500.01")
        self.assertEqual(self.ids(min_price="100", max_price="500"), {lower.pk, upper.pk})
        self.assertEqual(self.ids(min_price="500", max_price="500"), {upper.pk})
        self.assertEqual(len(self.ids(min_price="0")), 4)

    def test_text_attribute_matches_literal_substring_without_case(self):
        match = self.make_listing(attribute_values={"brand": "EXAMPLE% Brand"})
        self.make_listing(attribute_values={"brand": "Another brand"})
        self.make_listing(attribute_values={"brand": None})
        self.assertEqual(self.ids(category=self.laptops.pk, **{"attr.brand": "example%"}), {match.pk})
        self.assertEqual(self.ids(category=self.laptops.pk, **{"attr.brand": "null"}), set())

    def test_number_attribute_compares_numeric_values_not_strings(self):
        matches = [self.make_listing(attribute_values={"memory": value}) for value in (16, 16.0, "16.00")]
        self.make_listing(attribute_values={"memory": 160})
        self.assertEqual(self.ids(category=self.laptops.pk, **{"attr.memory": "16.0"}), {item.pk for item in matches})

    def test_missing_and_empty_numeric_values_do_not_match_zero(self):
        match = self.make_listing(attribute_values={"memory": 0})
        for values in ({}, {"memory": None}, {"memory": ""}):
            self.make_listing(attribute_values=values)
        self.assertEqual(self.ids(category=self.laptops.pk, **{"attr.memory": "0"}), {match.pk})

    def test_choice_attributes_match_exact_option_and_selected_category(self):
        match = self.make_listing(category=self.chairs, attribute_values={"material": "wood"})
        self.make_listing(category=self.chairs, attribute_values={"material": "metal"})
        self.assertEqual(self.ids(category=self.chairs.pk, **{"attr.material": "wood"}), {match.pk})

    def test_invalid_filters_return_clear_field_errors(self):
        for filters, field in (
            ({"currency": "ZZZ"}, "currency"), ({"currency": ""}, "currency"),
            ({"category": 999999}, "category"), ({"category": self.parent.pk}, "category"),
            ({"condition": "broken"}, "condition"), ({"min_price": "-1"}, "min_price"),
            ({"max_price": "NaN"}, "max_price"), ({"min_price": "Infinity"}, "min_price"),
            ({"min_price": "abc"}, "min_price"), ({"max_price": "1.234"}, "max_price"),
            ({"min_price": "501", "max_price": "500"}, "max_price"),
            ({"page": "0"}, "page"), ({"page": "abc"}, "page"),
            ({"page_size": "0"}, "page_size"), ({"page_size": "101"}, "page_size"),
            ({"ordering": "seller"}, "ordering"), ({"unexpected": "value"}, "unexpected"),
        ):
            with self.subTest(filters=filters):
                response = self.client.get(self.url, filters)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.data[field])

    def test_invalid_or_nonsearchable_attributes_are_rejected(self):
        for filters in (
            {"attr.brand": "Example"},
            {"category": self.chairs.pk, "attr.brand": "Example"},
            {"category": self.laptops.pk, "attr.serial": "123"},
            {"category": self.laptops.pk, "attr.unknown": "x"},
            {"category": self.laptops.pk, "attr.memory": "NaN"},
            {"category": self.laptops.pk, "attr.memory": "-1"},
            {"category": self.laptops.pk, "attr.memory": "1025"},
            {"category": self.laptops.pk, "attr.finish": "gold"},
        ):
            with self.subTest(filters=filters):
                response = self.client.get(self.url, filters)
                self.assertEqual(response.status_code, 400)
                attribute = next(key for key in filters if key.startswith("attr."))
                self.assertTrue(response.data[attribute])

    def test_multiple_values_for_one_filter_are_rejected(self):
        response = self.client.get(self.url + "?currency=CAD&currency=USD")
        self.assertEqual(response.status_code, 400)
        self.assertIn("currency", response.data)
        response = self.client.get(self.url + f"?category={self.laptops.pk}&attr.memory=8&attr.memory=16")
        self.assertEqual(response.status_code, 400)
        self.assertIn("attr.memory", response.data)

    def test_sorting_prices_only_compares_the_selected_currency(self):
        cheaper = self.make_listing(price="20.00")
        expensive = self.make_listing(price="100.00")
        self.make_listing(currency="USD", price="1.00")
        for ordering, expected in (("price", [cheaper.pk, expensive.pk]), ("-price", [expensive.pk, cheaper.pk])):
            response = self.client.get(self.url, {"ordering": ordering})
            self.assertEqual([row["id"] for row in response.data["results"]], expected)
            self.assertTrue(all(row["currency"] == "CAD" for row in response.data["results"]))

    def test_filters_do_not_expose_unavailable_listings(self):
        match = self.make_listing()
        for state in ("draft", "paused", "sold_out", "ended", "removed"):
            self.make_listing(state=state)
        self.make_listing(quantity=0)
        self.make_listing(ends_at=timezone.now() - timedelta(seconds=1))
        self.make_listing(seller=self.other)
        type(self.other).objects.filter(pk=self.other.pk).update(account_state="Suspended")
        self.assertEqual(self.ids(q="laptop", category=self.laptops.pk), {match.pk})
