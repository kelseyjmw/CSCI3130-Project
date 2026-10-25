from catalog.models import Category, CategoryAttribute, Listing
from tests.catalog.helpers import CatalogAPITestCase


class CatalogResultTests(CatalogAPITestCase):
    url = "/api/catalog/listings/"

    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name="Result laptops")
        Listing.objects.filter(pk=self.listing.pk).update(
            state="active", quantity=1, title="Working laptop", category=self.category,
            price="200.00", currency="CAD", condition="used_good",
        )

    def test_result_contains_only_the_five_card_fields_and_correct_primary_image(self):
        first = self.upload().data
        second = self.upload().data
        self.client.force_authenticate(None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row, {
            "id": self.listing.pk, "title": "Working laptop", "primary_image": first["file"],
            "price": "200.00", "currency": "CAD",
        })
        detail = self.client.get(f"/api/catalog/listings/{row['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["id"], row["id"])
        self.client.force_authenticate(self.seller)
        self.client.patch(self.images + "reorder/", {"image_ids": [second["id"], first["id"]]}, format="json")
        self.assertEqual(self.client.get(self.url).data["results"][0]["primary_image"], second["file"])

    def test_missing_primary_image_is_null(self):
        row = self.client.get(self.url).data["results"][0]
        self.assertIsNone(row["primary_image"])

    def test_filtered_count_covers_all_pages_and_filters_are_kept_in_next_link(self):
        CategoryAttribute.objects.create(
            category=self.category, code="result_memory", name="Memory", type="number", filterable=True,
        )
        Listing.objects.filter(pk=self.listing.pk).update(attribute_values={"result_memory": 16})
        fields = {
            "seller": self.seller, "state": "active", "quantity": 1, "title": "Working laptop",
            "category": self.category, "price": "200.00", "currency": "CAD", "condition": "used_good",
            "attribute_values": {"result_memory": 16},
        }
        Listing.objects.bulk_create([Listing(**fields) for _ in range(12)])
        for overrides in ({"currency": "USD"}, {"state": "paused"}, {"price": "300.00"}, {"attribute_values": {"result_memory": 8}}):
            Listing.objects.create(**(fields | overrides))
        filters = {
            "q": "laptop", "category": self.category.pk, "currency": "CAD", "condition": "used_good",
            "min_price": "200", "max_price": "200", "attr.result_memory": "16",
        }
        first = self.client.get(self.url, filters)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["count"], 13)
        self.assertEqual(len(first.data["results"]), 12)
        second = self.client.get(first.data["next"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["count"], 13)
        self.assertEqual(len(second.data["results"]), 1)
        self.assertIsNone(second.data["next"])
        self.assertIsNotNone(second.data["previous"])
        self.assertFalse({row["id"] for row in first.data["results"]} & {row["id"] for row in second.data["results"]})

    def test_page_size_and_out_of_range_page(self):
        Listing.objects.create(seller=self.seller, state="active", quantity=1, currency="CAD")
        response = self.client.get(self.url, {"page_size": 1})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(self.client.get(self.url, {"page": 99}).status_code, 404)

    def test_zero_matches_return_zero_count_and_empty_results(self):
        response = self.client.get(self.url, {"q": "no-such-title"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"count": 0, "total_pages": 1, "next": None, "previous": None, "results": []})
