from django.db import migrations


def seed(apps, schema_editor):
    Permission = apps.get_model("security", "Permission")
    Role = apps.get_model("security", "Role")
    for code in ("listings.create", "listings.edit"):
        permission, _ = Permission.objects.get_or_create(code=code)
        for name in ("Seller", "Administrator"):
            role, _ = Role.objects.get_or_create(name=name)
            role.permissions.add(permission)


def unseed(apps, schema_editor):
    apps.get_model("security", "Permission").objects.filter(
        code__in=["listings.create", "listings.edit"],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("security", "0003_loginfailure")]
    operations = [migrations.RunPython(seed, unseed)]
