from django.db import migrations

PERMISSIONS = [
    "listings.view",
    "items.buy",
    "listings.publish",
    "messages.send",
    "listings.report",
    "listings.remove",
    "sellers.approve",
    "accounts.suspend",
    "accounts.change_roles",
    "audit.read",
]

ROLES = {
    "Buyer": [
        "listings.view",
        "items.buy",
        "messages.send",
        "listings.report",
    ],
    "Seller": [
        "listings.view",
        "items.buy",
        "listings.publish",
        "messages.send",
        "listings.report",
    ],
    "Moderator": [
        "listings.view",
        "items.buy",
        "messages.send",
        "listings.report",
        "listings.remove",
        "sellers.approve",
        "accounts.suspend",
    ],
    "Administrator": PERMISSIONS,
}


def seed(apps, schema_editor):
    Permission = apps.get_model("security", "Permission")
    Role = apps.get_model("security", "Role")
    perms = {}
    for code in PERMISSIONS:
        perms[code], _ = Permission.objects.get_or_create(code=code)
    for name, codes in ROLES.items():
        role, _ = Role.objects.get_or_create(name=name)
        role.permissions.set([perms[code] for code in codes])


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("security", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
