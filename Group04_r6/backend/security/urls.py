from django.urls import path

from .views import (
    AccountStateListView,
    AccountStateView,
    ProtectedView,
    UserListView,
    UserRolesView,
)

urlpatterns = [
    path("api/protected/", ProtectedView.as_view()),
    path("api/security/users/", UserListView.as_view()),
    path("api/security/users/<int:user_id>/", UserRolesView.as_view()),
    path("api/security/account-state/", AccountStateListView.as_view()),
    path("api/security/account-state/<int:user_id>/", AccountStateView.as_view()),
]
