from django.urls import path

from .views import (
    CategoryAttributeListView, CategoryListView, ListingCreateView, ListingDetailView,
    ListingImageDetailView, ListingImageFileView, ListingImageOrderView,
    ListingImageUploadView, ListingStateActionView, MyListingsView,
)

app_name = "catalog"

urlpatterns = [
    path("listings/", ListingCreateView.as_view(), name="listing-create"),
    path("listings/mine/", MyListingsView.as_view(), name="my-listings"),
    path("listings/<int:pk>/", ListingDetailView.as_view(), name="listing-detail"),
    path("listings/<int:pk>/publish/", ListingStateActionView.as_view(listing_action="publish"), name="listing-publish"),
    path("listings/<int:pk>/pause/", ListingStateActionView.as_view(listing_action="pause"), name="listing-pause"),
    path("listings/<int:pk>/resume/", ListingStateActionView.as_view(listing_action="resume"), name="listing-resume"),
    path("listings/<int:pk>/end/", ListingStateActionView.as_view(listing_action="end"), name="listing-end"),
    path("listings/<int:pk>/remove/", ListingStateActionView.as_view(listing_action="remove"), name="listing-remove"),
    path("listings/<int:pk>/images/", ListingImageUploadView.as_view(), name="image-upload"),
    path("listings/<int:pk>/images/reorder/", ListingImageOrderView.as_view(), name="image-order"),
    path("listings/<int:pk>/images/<int:image_id>/", ListingImageDetailView.as_view(), name="image-detail"),
    path("listings/<int:pk>/images/<int:image_id>/file/", ListingImageFileView.as_view(), name="image-file"),
    path("categories/", CategoryListView.as_view(), name="categories"),
    path(
        "categories/<int:pk>/attributes/",
        CategoryAttributeListView.as_view(),
        name="category-attributes",
    ),
]
