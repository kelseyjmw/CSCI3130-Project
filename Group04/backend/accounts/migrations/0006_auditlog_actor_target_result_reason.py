from django.db import migrations, models
from django.db.models import F

# Action values used before the audit logger, mapped to log.audit_logger.LogType values.
OLD_ACTIONS = {
    "LOGIN": "login",
    "LOGOUT": "logout",
    "PASSWORD_CHANGE": "password_changes",
    "PASSWORD_RESET": "password_reset",
}


def copy_existing_records(apps, schema_editor):
    # Existing records only came from successful log-ins and log-outs, where the user is both actor and target.
    AuditLog = apps.get_model("accounts", "AuditLog")
    AuditLog.objects.update(actor=F("user_id"), target=F("user_id"))
    for old, new in OLD_ACTIONS.items():
        AuditLog.objects.filter(action=old).update(action=new)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_user_session_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='actor',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='target',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='result',
            field=models.CharField(default='success', max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='auditlog',
            name='reason',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='auditlog',
            name='action',
            field=models.CharField(max_length=50),
        ),
        migrations.RunPython(copy_existing_records, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='auditlog',
            name='user',
        ),
        migrations.AlterModelOptions(
            name='auditlog',
            options={'ordering': ['-timestamp', '-id']},
        ),
    ]
