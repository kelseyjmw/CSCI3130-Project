from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, pre_save
from django.dispatch import receiver

from .models import Role

ADMIN_ROLE = "Administrator"


def is_usable_admin(user):
    return (
        user.is_active
        and getattr(user, "account_state", "Active") == "Active"
    )


def active_admin_count(exclude_user=None):
    qs = get_user_model().objects.filter(
        is_active=True, account_state="Active", roles__name=ADMIN_ROLE
    ).distinct()
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    return qs.count()


@receiver(m2m_changed, sender=Role.users.through)
def protect_last_admin_role(sender, instance, action, pk_set, **kwargs):
    if instance.name != ADMIN_ROLE:
        return
    if action == "pre_remove" and pk_set:
        left = instance.users.filter(
            is_active=True, account_state="Active"
        ).exclude(pk__in=pk_set).count()
        if left < 1:
            raise ValidationError("Cannot remove the last active administrator.")
    if action == "pre_clear" and instance.users.filter(
        is_active=True, account_state="Active"
    ).exists():
        raise ValidationError("Cannot remove the last active administrator.")


@receiver(pre_save, sender="accounts.User")
def protect_last_admin_account(sender, instance, **kwargs):
    if not instance.pk:
        return
    still_usable = instance.is_active and instance.account_state == "Active"
    if still_usable:
        return
    User = get_user_model()
    old = User.objects.filter(pk=instance.pk).first()
    if old is None or not is_usable_admin(old):
        return
    if old.roles.filter(name=ADMIN_ROLE).exists() and active_admin_count(exclude_user=old) < 1:
        raise ValidationError("Cannot close or suspend the last active administrator.")
