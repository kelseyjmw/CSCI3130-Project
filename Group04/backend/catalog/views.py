from mimetypes import guess_type

from django.db import transaction
from django.db.models import F, Max, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListCreateAPIView, ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from security.permissions import HasPermission

from .models import Category, Listing, ListingImage
from .filters import filter_listings
from .editing import validate_listing_edit
from .permissions import CanChangeListing, CanCreateListing, can_view_listing
from .services import change_listing_state, process_listing_states, refresh_listing_state
from .serializers import (
    CategoryAttributeSerializer, CategorySerializer, ImageDescriptionSerializer,
    ImageOrderSerializer, ImageUploadSerializer, ListingImageSerializer,
    ListingResultSerializer, ListingSerializer,
)

class ListingPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["total_pages"] = self.page.paginator.num_pages
        return response


class CategoryListView(ListAPIView):
    permission_classes = [HasPermission]
    required_permission = "listings.view"
    serializer_class = CategorySerializer
    queryset = Category.objects.order_by("name", "pk")


class CategoryAttributeListView(ListAPIView):
    permission_classes = [HasPermission]
    required_permission = "listings.view"
    serializer_class = CategoryAttributeSerializer

    def get_queryset(self):
        category = get_object_or_404(Category, pk=self.kwargs["pk"])
        return category.attributes.order_by("code")


class ListingCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated, CanCreateListing]
    serializer_class = ListingSerializer
    pagination_class = ListingPagination

    def get_serializer_class(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return ListingResultSerializer
        return ListingSerializer

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        process_listing_states()
        queryset = Listing.objects.filter(
            state="active", quantity__gt=0, seller__is_active=True,
            seller__account_state="Active", seller__email_verified=True, seller__roles__name="Seller",
        ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now())).select_related("seller").prefetch_related("images").distinct()
        return filter_listings(queryset, self.request.query_params)


class MyListingsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ListingSerializer

    def get_queryset(self):
        process_listing_states()
        return Listing.objects.filter(seller=self.request.user).prefetch_related("images").order_by("-created_at", "-pk")


class ListingAccessView(APIView):
    permission_classes = [IsAuthenticated, CanChangeListing]

    def get_listing(self, pk, lock=False, images=False):
        if lock:
            # Serialize edits and image-count checks on SQLite as well as other DBs.
            Listing.objects.filter(pk=pk).update(updated_at=F("updated_at"))
        listing = get_object_or_404(Listing, pk=pk)
        self.check_object_permissions(self.request, listing)
        if lock and listing.state == Listing.State.REMOVED:
            raise ValidationError("Removed listings cannot be edited.")
        if images:
            validate_listing_edit(listing, images=True)
        return listing

    def image_data(self, image):
        return ListingImageSerializer(image, context={"request": self.request}).data

    def get_visible_listing(self, pk):
        listing = refresh_listing_state(pk)
        if not can_view_listing(self.request.user, listing):
            raise PermissionDenied("This listing is not publicly available.")
        return listing


class ListingDetailView(ListingAccessView):
    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return super().get_permissions()

    def get(self, request, pk):
        listing = self.get_visible_listing(pk)
        return Response(ListingSerializer(listing, context={"request": request}).data)

    @transaction.atomic
    def patch(self, request, pk):
        listing = self.get_listing(pk, lock=True)
        serializer = ListingSerializer(listing, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ListingStateActionView(APIView):
    permission_classes = [IsAuthenticated, CanChangeListing]
    listing_action = None

    def post(self, request, pk):
        if request.data:
            raise ValidationError("This action does not accept listing fields.")
        listing = change_listing_state(pk, self.listing_action, request.user)
        return Response(ListingSerializer(listing, context={"request": request}).data)


class ListingImageUploadView(ListingAccessView):
    @transaction.atomic
    def post(self, request, pk):
        listing = self.get_listing(pk, lock=True, images=True)
        if listing.images.count() >= 5:
            raise ValidationError({"file": "A listing can have at most five images."})
        serializer = ImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        last_position = listing.images.aggregate(last=Max("position"))["last"]
        image = ListingImage(
            listing=listing, position=0 if last_position is None else last_position + 1,
            **serializer.validated_data,
        )
        try:
            image.save()
            listing.save(update_fields=["updated_at"])
            data = self.image_data(image)
        except Exception:
            if image.file._committed:
                image.file.delete(save=False)
            raise
        return Response(data, status=201)


class ListingImageDetailView(ListingAccessView):
    @transaction.atomic
    def patch(self, request, pk, image_id):
        listing = self.get_listing(pk, lock=True, images=True)
        image = get_object_or_404(listing.images, pk=image_id)
        serializer = ImageDescriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image.description = serializer.validated_data["description"]
        image.save(update_fields=["description"])
        listing.save(update_fields=["updated_at"])
        return Response(self.image_data(image))

    @transaction.atomic
    def delete(self, request, pk, image_id):
        listing = self.get_listing(pk, lock=True, images=True)
        image = get_object_or_404(listing.images, pk=image_id)
        published = listing.published_at is not None or listing.state != Listing.State.DRAFT
        if published and listing.images.count() <= 1:
            raise ValidationError("A published listing must keep at least one image.")
        image.delete()
        transaction.on_commit(lambda: image.file.delete(save=False))
        listing.save(update_fields=["updated_at"])
        return Response(status=204)


class ListingImageOrderView(ListingAccessView):
    @transaction.atomic
    def patch(self, request, pk):
        listing = self.get_listing(pk, lock=True, images=True)
        serializer = ImageOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["image_ids"]
        images = {image.pk: image for image in listing.images.all()}
        if set(ids) != set(images):
            raise ValidationError({"image_ids": "Include every image of this listing exactly once."})
        for position, image_id in enumerate(ids):
            images[image_id].position = position
        if images:
            ListingImage.objects.bulk_update(images.values(), ["position"])
        listing.save(update_fields=["updated_at"])
        return Response(ListingImageSerializer(listing.images.all(), many=True, context={"request": request}).data)


class ListingImageFileView(ListingAccessView):
    permission_classes = [AllowAny]

    def get(self, request, pk, image_id):
        listing = self.get_visible_listing(pk)
        image = get_object_or_404(listing.images, pk=image_id)
        try:
            response = FileResponse(image.file.open("rb"), content_type=guess_type(image.file.name)[0])
        except FileNotFoundError:
            raise Http404("Image file not found.")
        response["Cache-Control"] = "private, no-store"
        return response
