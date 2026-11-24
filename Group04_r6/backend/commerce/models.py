from django.conf import settings
from django.db import models


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cart', null=True, blank=True,
    )
    session_key = models.CharField(max_length=40, null=True, blank=True)
    display_currency = models.CharField(max_length=3, default='CAD')
    checking_out = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['session_key'],
                condition=models.Q(session_key__isnull=False),
                name='one_cart_per_session',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, session_key__isnull=True)
                    | models.Q(user__isnull=True, session_key__isnull=False)
                ),
                name='cart_belongs_to_user_or_session',
            ),
        ]


class CartLine(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='lines')
    listing = models.ForeignKey('catalog.Listing', on_delete=models.PROTECT, related_name='cart_lines')
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cart', 'listing'], name='one_cart_line_per_listing'),
        ]


class Order(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name='orders')
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders', null=True, blank=True,
    )
    session_key = models.CharField(max_length=40, null=True, blank=True)
    payment_status = models.CharField(max_length=20, default='Pending')
    display_currency = models.CharField(max_length=3)
    display_subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    display_tax = models.DecimalField(max_digits=12, decimal_places=2)
    display_delivery = models.DecimalField(max_digits=12, decimal_places=2)
    display_total = models.DecimalField(max_digits=12, decimal_places=2)
    buyer_currency = models.CharField(max_length=3)
    buyer_total = models.DecimalField(max_digits=12, decimal_places=2)
    guest_email = models.CharField(max_length=254, blank=True, default='')
    access_token_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cart'],
                condition=models.Q(payment_status='Pending'),
                name='one_pending_order_per_cart',
            ),
        ]


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='lines')
    listing = models.ForeignKey('catalog.Listing', on_delete=models.PROTECT)
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='order_lines')
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)


class OrderSellerShare(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='seller_shares')
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='order_shares')
    item_subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax = models.DecimalField(max_digits=12, decimal_places=2)
    delivery = models.DecimalField(max_digits=12, decimal_places=2)
    share = models.DecimalField(max_digits=12, decimal_places=2)
    credit = models.DecimalField(max_digits=12, decimal_places=2)
    credit_currency = models.CharField(max_length=3)


class OrderAddress(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='address')
    full_name = models.CharField(max_length=200)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)


class AuctionOrderSettlement(models.Model):
    auction_order = models.OneToOneField(
        'catalog.AuctionOrder', on_delete=models.PROTECT, related_name='settlement',
    )
    item_subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax = models.DecimalField(max_digits=12, decimal_places=2)
    delivery = models.DecimalField(max_digits=12, decimal_places=2)
    buyer_total = models.DecimalField(max_digits=12, decimal_places=2)
    buyer_currency = models.CharField(max_length=3)
    seller_credit = models.DecimalField(max_digits=12, decimal_places=2)
    seller_currency = models.CharField(max_length=3)
    full_name = models.CharField(max_length=200)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    paid_at = models.DateTimeField(auto_now_add=True)