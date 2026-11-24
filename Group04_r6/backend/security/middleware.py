from django.contrib.auth import logout
from django.http import JsonResponse

from accounts.two_factor import is_administrator


MFA_SETUP_PATHS = {
    "/api/accounts/csrf/",
    "/api/accounts/login/",
    "/api/accounts/login/verify-mfa/",
    "/api/accounts/logout/",
    "/api/accounts/two-factor/setup/",
    "/api/accounts/two-factor/confirm/",
}


class RequireAdminTwoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path not in MFA_SETUP_PATHS
            and request.user.is_authenticated
            and is_administrator(request.user)
            and not request.user.totp_enabled
        ):
            logout(request)
            return JsonResponse(
                {"error": "Administrators must enable two-factor authentication."},
                status=403,
            )
        return self.get_response(request)
