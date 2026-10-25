from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Category, CategoryAttribute


class Command(BaseCommand):
    help = "Create or update the initial categories and attributes without duplicates."

    @transaction.atomic
    def handle(self, *args, **options):
        categories = [
            ("Laptops", "laptop", 1024, 65536),
            ("Desktops", "desktop", 4096, 262144),
        ]
        electronics, _ = Category.objects.get_or_create(name="Electronics", parent=None)
        computers, _ = Category.objects.get_or_create(name="Computers", parent=electronics)
        for name, prefix, max_memory, max_storage in categories:
            category, _ = Category.objects.get_or_create(name=name, parent=computers)
            self.attribute(category, f"{prefix}_brand", "Brand", "text")
            self.attribute(
                category, f"{prefix}_memory_gb", "Memory (GB)", "number",
                min_value=0, max_value=max_memory,
            )
            self.attribute(
                category, f"{prefix}_storage_gb", "Storage (GB)", "number",
                min_value=0, max_value=max_storage,
            )

        home, _ = Category.objects.get_or_create(name="Home", parent=None)
        furniture, _ = Category.objects.get_or_create(name="Furniture", parent=home)
        chairs, _ = Category.objects.get_or_create(name="Chairs", parent=furniture)
        self.attribute(
            chairs, "chair_material", "Material", "choice",
            options=["wood", "metal", "plastic", "fabric", "leather", "other"],
        )
        self.attribute(
            chairs, "chair_color", "Color", "text", required=False, filterable=False,
        )
        self.stdout.write(self.style.SUCCESS("Catalog seed data ready."))

    def attribute(self, category, code, name, type, **rules):
        CategoryAttribute.objects.update_or_create(
            code=code,
            defaults={
                "category": category,
                "name": name,
                "type": type,
                "required": True,
                "filterable": True,
                "min_value": None,
                "max_value": None,
                "options": [],
                **rules,
            },
        )
