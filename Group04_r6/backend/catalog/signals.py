from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


@receiver(pre_save, sender='accounts.User')
def detect_auction_suspension(sender, instance, update_fields=None, raw=False, **kwargs):
    instance._auction_suspended = False
    if raw or not instance.pk or instance.account_state != 'Suspended':
        return
    if update_fields is not None and 'account_state' not in update_fields:
        return
    instance._auction_suspended = sender.objects.filter(pk=instance.pk).exclude(account_state='Suspended').exists()


@receiver(post_save, sender='accounts.User')
def apply_auction_suspension(sender, instance, raw=False, **kwargs):
    if not raw and getattr(instance, '_auction_suspended', False):
        from .auctions import handle_account_suspension
        handle_account_suspension(instance.pk)
