from datetime import timedelta

from django.utils import timezone

from catalog.models import Category, Listing
from tests.catalog.helpers import CatalogAPITestCase


class ListingPaginationTests(CatalogAPITestCase):
    url = "/api/catalog/listings/"

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(None)
        self.category = Category.objects.create(name="Laptops")

    def make_listings(self, count, **overrides):
        """Create `count` visible listings. Index 0 is the oldest, and prices rise with the index."""
        now = timezone.now()
        listings = []
        for index in range(count):
            fields = {
                "seller": self.seller, "state": "active", "title": f"Laptop {index}",
                "description": "A working laptop with complete details.", "category": self.category,
                "price": f"{index + 1}.00", "currency": "CAD", "quantity": 1,
                "condition": "used_good", "attribute_values": {},
            }
            fields.update(overrides)
            listing = Listing.objects.create(**fields)
            # Written directly so it holds even if published_at is set automatically on save.
            Listing.objects.filter(pk=listing.pk).update(published_at=now - timedelta(minutes=count - index))
            listings.append(listing)
        return listings

    def all_ids(self, **params):
        """Ids from every page, in the order the API returned them."""
        ids, page = [], 1
        while True:
            response = self.client.get(self.url, {**params, "page": page})
            self.assertEqual(response.status_code, 200, response.data)
            ids += [row["id"] for row in response.data["results"]]
            if response.data["next"] is None:
                return ids
            page += 1

    def test_first_page_has_twelve_listings_and_the_totals(self):
        self.make_listings(30)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 12)
        self.assertEqual(response.data["count"], 30)
        self.assertEqual(response.data["total_pages"], 3)
        self.assertIsNone(response.data["previous"])
        self.assertIsNotNone(response.data["next"])

    def test_last_page_has_the_remaining_listings(self):
        self.make_listings(30)
        response = self.client.get(self.url, {"page": 3})
        self.assertEqual(len(response.data["results"]), 6)
        self.assertIsNone(response.data["next"])
        self.assertIsNotNone(response.data["previous"])

    def test_no_listings_gives_one_empty_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["total_pages"], 1)
        self.assertEqual(response.data["results"], [])

    def test_newest_order_continues_across_pages_without_gaps_or_repeats(self):
        listings = self.make_listings(30)
        self.assertEqual(self.all_ids(), [item.pk for item in reversed(listings)])

    def test_price_order_continues_across_pages(self):
        listings = self.make_listings(30)
        self.assertEqual(self.all_ids(ordering="price"), [item.pk for item in listings])
        self.assertEqual(self.all_ids(ordering="-price"), [item.pk for item in reversed(listings)])

    def test_equal_prices_keep_a_stable_order_across_pages(self):
        listings = self.make_listings(15, price="10.00")
        self.assertEqual(self.all_ids(ordering="price"), sorted(item.pk for item in listings))

    def test_filters_apply_to_the_counts_and_pages(self):
        self.make_listings(14)
        self.make_listings(5, title="Office chair", description="An office chair in good condition.")
        response = self.client.get(self.url, {"q": "laptop"})
        self.assertEqual(response.data["count"], 14)
        self.assertEqual(response.data["total_pages"], 2)
        self.assertEqual(len(self.client.get(self.url, {"q": "laptop", "page": 2}).data["results"]), 2)

    def test_next_link_keeps_the_filters_and_sort(self):
        self.make_listings(30)
        response = self.client.get(self.url, {"q": "laptop", "ordering": "price"})
        self.assertIn("q=laptop", response.data["next"])
        self.assertIn("ordering=price", response.data["next"])
        self.assertIn("page=2", response.data["next"])

    def test_page_past_the_end_is_not_found(self):
        self.make_listings(3)
        self.assertEqual(self.client.get(self.url, {"page": 2}).status_code, 404)

    def test_invalid_page_values_are_rejected(self):
        for page in ("0", "-1", "abc"):
            with self.subTest(page=page):
                response = self.client.get(self.url, {"page": page})
                self.assertEqual(response.status_code, 400)
                self.assertIn("page", response.data)

    def test_page_size_remains_configurable_for_existing_api_clients(self):
        self.make_listings(30)
        response = self.client.get(self.url, {"page_size": 30})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 30)
        self.assertEqual(response.data["total_pages"], 1)

    def test_unavailable_listings_are_not_counted(self):
        self.make_listings(3)
        for state in ("draft", "paused", "ended"):
            self.make_listings(1, state=state)
        self.assertEqual(self.client.get(self.url).data["count"], 3)

    def test_my_listings_stays_a_plain_list(self):
        self.make_listings(15, state="draft")
        self.client.force_authenticate(self.seller)
        response = self.client.get(f"{self.url}mine/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertGreaterEqual(len(response.data), 15)
