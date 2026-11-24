from django.urls import path

from .views import (
    AuctionOrderDetailView, AuctionOrderPayView, AuctionOrderQuoteView,
    CartCurrencyView, CartItemDeleteView, CartItemView, CartView,
    CheckoutAddressView, CheckoutConfirmView, CheckoutRecheckView, CheckoutReturnView,
    CheckoutReviewView, CheckoutStartView, GuestOrderView, OrderDetailView, OrderPayView,
)

app_name = 'commerce'

urlpatterns = [
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/items/', CartItemView.as_view(), name='cart-items'),
    path('cart/items/<int:listing_id>/', CartItemDeleteView.as_view(), name='cart-item-delete'),
    path('cart/currency/', CartCurrencyView.as_view(), name='cart-currency'),
    path('checkout/', CheckoutStartView.as_view(), name='checkout-start'),
    path('checkout/review/', CheckoutReviewView.as_view(), name='checkout-review'),
    path('checkout/confirm/', CheckoutConfirmView.as_view(), name='checkout-confirm'),
    path('checkout/return/', CheckoutReturnView.as_view(), name='checkout-return'),
    path('checkout/address/', CheckoutAddressView.as_view(), name='checkout-address'),
    path('checkout/recheck/', CheckoutRecheckView.as_view(), name='checkout-recheck'),
    path('orders/guest/<str:token>/', GuestOrderView.as_view(), name='guest-order'),
    path('orders/<int:order_id>/', OrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:order_id>/pay/', OrderPayView.as_view(), name='order-pay'),
    path('auction-orders/<int:auction_order_id>/', AuctionOrderDetailView.as_view(), name='auction-order-detail'),
    path('auction-orders/<int:auction_order_id>/quote/', AuctionOrderQuoteView.as_view(), name='auction-order-quote'),
    path('auction-orders/<int:auction_order_id>/pay/', AuctionOrderPayView.as_view(), name='auction-order-pay'),
]
