from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Listing

from .cart import (
    _get_cart, add_to_cart, cart_display, cart_warnings, remove_from_cart,
    set_display_currency, set_quantity,
)
from .checkout import (
    confirm_checkout, recheck_before_payment, return_to_cart, review_checkout,
    save_delivery_address, start_checkout, view_guest_order, view_order,
)
from .models import Cart, Order
from .payment import pay_auction_order, pay_order, quote_auction_order, view_auction_order


def _actor(request, create_session=False):
    if request.user.is_authenticated:
        return request.user, None
    if create_session and not request.session.session_key:
        request.session.save()
    return None, request.session.session_key


def _error(exc, status=400):
    message = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
    return Response({'detail': message}, status=status)


def _plain(value):
    if isinstance(value, Decimal):
        return f'{value:.2f}'
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _quantity(value):
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        raise DjangoValidationError('Quantity must be positive.')
    if quantity < 1:
        raise DjangoValidationError('Quantity must be positive.')
    return quantity


def _cart_response(request):
    buyer, session_key = _actor(request)
    if buyer is None and not session_key:
        return _empty_cart()
    shown = cart_display(buyer, session_key)
    warnings = cart_warnings(buyer, session_key)
    if buyer is not None:
        cart = Cart.objects.filter(user=buyer).first()
    else:
        cart = Cart.objects.filter(session_key=session_key, user__isnull=True).first()
    titles = dict(
        Listing.objects.filter(pk__in=[row['listing_id'] for row in shown['lines']]).values_list('pk', 'title')
    )
    return {
        'currency': shown['currency'],
        'lines': [
            {
                'listing_id': row['listing_id'],
                'title': titles.get(row['listing_id'], ''),
                'quantity': row['quantity'],
                'unit_price': f'{row["unit_price"]:.2f}',
                'line_total': f'{row["line_total"]:.2f}',
            }
            for row in shown['lines']
        ],
        'total': f'{shown["total"]:.2f}',
        'warnings': warnings,
        'checking_out': bool(cart and cart.checking_out),
    }


def _empty_cart():
    return {
        'currency': 'CAD',
        'lines': [],
        'total': '0.00',
        'warnings': [],
        'checking_out': False,
    }


def _review_payload(buyer, session_key):
    shown = _plain(review_checkout(buyer, session_key))
    cart = _get_cart(buyer, session_key)
    order = None if cart is None else Order.objects.filter(cart=cart, payment_status='Pending').first()
    shown['order_id'] = None if order is None else order.pk
    return shown


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CartView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            return Response(_cart_response(request))
        except DjangoValidationError as exc:
            return _error(exc)


class CartItemView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        buyer, session_key = _actor(request, create_session=True)
        listing = get_object_or_404(Listing, pk=request.data.get('listing_id'))
        try:
            add_to_cart(buyer, listing, _quantity(request.data.get('quantity', 1)), session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(_cart_response(request))

    def patch(self, request):
        buyer, session_key = _actor(request)
        listing = get_object_or_404(Listing, pk=request.data.get('listing_id'))
        try:
            set_quantity(buyer, listing, _quantity(request.data.get('quantity')), session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(_cart_response(request))


class CartItemDeleteView(APIView):
    permission_classes = [AllowAny]

    def delete(self, request, listing_id):
        buyer, session_key = _actor(request)
        listing = get_object_or_404(Listing, pk=listing_id)
        try:
            remove_from_cart(buyer, listing, session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(_cart_response(request))


class CartCurrencyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        buyer, session_key = _actor(request, create_session=True)
        try:
            set_display_currency(buyer, request.data.get('currency'), session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(_cart_response(request))


class CheckoutStartView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        buyer, session_key = _actor(request)
        try:
            order = start_checkout(buyer, session_key, guest_email=request.data.get('guest_email'))
            payload = _review_payload(buyer, session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        payload['guest_access_token'] = getattr(order, 'guest_access_token', None)
        return Response(payload)


class CheckoutReviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        buyer, session_key = _actor(request)
        try:
            return Response(_review_payload(buyer, session_key))
        except DjangoValidationError as exc:
            return _error(exc)


class CheckoutConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        buyer, session_key = _actor(request)
        try:
            confirm_checkout(buyer, session_key)
            return Response(_review_payload(buyer, session_key))
        except DjangoValidationError as exc:
            return _error(exc)


class CheckoutReturnView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        buyer, session_key = _actor(request)
        return_to_cart(buyer, session_key)
        return Response(_cart_response(request))


class CheckoutAddressView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        buyer, session_key = _actor(request)
        try:
            save_delivery_address(buyer, request.data, session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response({'saved': True})


class OrderDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        viewer = request.user if request.user.is_authenticated else None
        try:
            return Response(_plain(view_order(order, viewer)))
        except DjangoValidationError as exc:
            return _error(exc, status=403)


class GuestOrderView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            return Response(_plain(view_guest_order(token=token)))
        except DjangoValidationError as exc:
            return _error(exc, status=404)


class CheckoutRecheckView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        buyer, session_key = _actor(request)
        try:
            order = recheck_before_payment(buyer, session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response({'order_id': order.pk, 'payment_status': order.payment_status})


class OrderPayView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, order_id):
        buyer, session_key = _actor(request)
        try:
            result = pay_order(order_id, buyer, session_key)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(_plain(result))


class AuctionOrderDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, auction_order_id):
        viewer = request.user if request.user.is_authenticated else None
        try:
            return Response(_plain(view_auction_order(auction_order_id, viewer)))
        except DjangoValidationError as exc:
            return _error(exc, status=403)


class AuctionOrderQuoteView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, auction_order_id):
        try:
            return Response(_plain(quote_auction_order(auction_order_id, request.user)))
        except DjangoValidationError as exc:
            return _error(exc)


class AuctionOrderPayView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, auction_order_id):
        address = request.data.get('address', request.data)
        try:
            result = pay_auction_order(auction_order_id, request.user, address)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(_plain(result))
