from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import generics, permissions, status  # pyright: ignore[reportMissingImports]
from rest_framework.response import Response  # pyright: ignore[reportMissingImports]
from rest_framework.views import APIView  # pyright: ignore[reportMissingImports]

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from log.audit_logger import Logger, LogResult, LogType

from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie
from rest_framework.parsers import FormParser, MultiPartParser  # pyright: ignore[reportMissingImports]
from django.utils.dateformat import format as date_format

from security.permissions import assign_buyer, grant_seller
from security.rate_limit import check_login_allowed, get_client_ip, record_login_failure

from .emails import (
    send_email_change_link,
    send_email_change_notice,
    send_verification_link,
    send_password_change_notice,
    send_password_reset_link,
    send_verification_link,
    )
from .models import (
    EmailVerification,
    SellerApplication,
    User,
    LoginHistory,
    AuditLog,
    PasswordResetToken,
    TwoFactorRecoveryCode,
)
from .two_factor import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    is_administrator,
    provisioning_uri,
    verify_totp,
)
from .serializers import (
    ChangePasswordSerializer,
    ChangeEmailSerializer,
    NewPasswordSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    SellerApplicationSerializer,
    MySellerApplicationSerializer,
    PendingSellerApplicationSerializer,
    PublicProfileSerializer,
    ProfileUpdateSerializer,
    AccountUpdateSerializer,
    AdminPanelAccountListSerializer,
    AuditLogSerializer,
    UserSerializer,
)
import json

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import BasePermission
from security.models import Role

from datetime import timezone as dt_timezone

from django.db.models import Q
from rest_framework.pagination import PageNumberPagination

from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import Wallet, WalletTransaction
from .serializers import (
    WalletSerializer,
    WalletCreateSerializer,
    WalletTopUpSerializer
)

INVALID_LINK = (
    'This link is no longer valid because it expired, was already used, or was replaced by a '
    'newer link. Request a new verification link.'
)
ADDRESS_TAKEN = (
    'That address is now associated with another account. Your current address is unchanged — '
    'choose another address.'
)

audit_logger = Logger()


def verification_link(request, viewname, raw_token):
    return request.build_absolute_uri(reverse(viewname, args=[raw_token]))


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        assign_buyer(user)
        _, raw_token = EmailVerification.issue(user, EmailVerification.Purpose.REGISTRATION)
        send_verification_link(
            user.email, verification_link(self.request, 'verify-email', raw_token)
        )
        

class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        verification = EmailVerification.resolve(token, EmailVerification.Purpose.REGISTRATION)
        if verification is None or not verification.is_valid:
            return Response({'detail': INVALID_LINK}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if not verification.consume():
                return Response({'detail': INVALID_LINK}, status=status.HTTP_400_BAD_REQUEST)
            user = verification.user
            user.email_verified = True
            user.save(update_fields=['email_verified'])
        return Response({'detail': 'Your email address is verified.'})


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(email=serializer.validated_data['email']).first()
        if user is not None and not user.email_verified:
            _, raw_token = EmailVerification.issue(user, EmailVerification.Purpose.REGISTRATION)
            send_verification_link(
                user.email, verification_link(request, 'verify-email', raw_token)
            )

        return Response(
            {'detail': 'If that account exists and is unverified, a new link has been sent.'}
        )


class ChangeEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangeEmailSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        new_email = serializer.validated_data['new_email']
        _, raw_token = EmailVerification.issue(
            request.user, EmailVerification.Purpose.EMAIL_CHANGE, new_email=new_email
        )
        send_email_change_link(
            new_email, verification_link(request, 'verify-email-change', raw_token)
        )
        return Response({'detail': f'A verification link was sent to {new_email}.'})


class VerifyEmailChangeView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        verification = EmailVerification.resolve(token, EmailVerification.Purpose.EMAIL_CHANGE)
        if verification is None or not verification.is_valid:
            return Response({'detail': INVALID_LINK}, status=status.HTTP_400_BAD_REQUEST)

        user = verification.user
        old_email = user.email
        new_email = verification.new_email

        try:
            with transaction.atomic():
                if not verification.consume():
                    return Response({'detail': INVALID_LINK}, status=status.HTTP_400_BAD_REQUEST)
                user.refresh_from_db()
                old_email = user.email
                taken = User.objects.filter(email=new_email).exclude(pk=user.pk).exists()
                if taken:
                    transaction.set_rollback(True)
                if not taken:
                    user.email = new_email
                    user.email_verified = True
                    user.save(update_fields=['email', 'email_verified'])

                    # Record the email change in the audit log
                    audit_logger.log(audit_logger.create_log_entry(LogType.EMAIL_CHANGE, {
                        "actor": user.pk,
                        "target": user.pk,
                        "result": LogResult.SUCCESS,
                        "reason": f"User changed email from {old_email} to {new_email}."
                    }))

        except IntegrityError:
            taken = True

        if taken:

            # Record the failed email change attempt in the audit log
            audit_logger.log(audit_logger.create_log_entry(LogType.EMAIL_CHANGE, {
                "actor": user.pk,
                "target": user.pk,
                "result": LogResult.FAILED,
                "reason": f"Failed attempt to change email from {old_email} to {new_email} because the new email is already taken."
            }))

            return Response({'detail': ADDRESS_TAKEN}, status=status.HTTP_400_BAD_REQUEST)

        send_email_change_notice(old_email, new_email)
        return Response({'detail': 'Your email address is updated and verified.'})


class SellerApplicationCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if SellerApplication.objects.filter(
            applicant=request.user,
            status=SellerApplication.Status.PENDING,
        ).exists():
            return Response(
                {'detail': 'You already have a pending seller application.'},
                status=status.HTTP_409_CONFLICT,
            )

        available_at = SellerApplication.reapply_available_at(request.user)
        if available_at is not None and timezone.now() < available_at:
            when = available_at.astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            return Response(
                {
                    'detail': f'Your last application was rejected. You can reapply after {when}.',
                    'available_at': available_at.isoformat(),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SellerApplicationSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                application = serializer.save()
        except IntegrityError:
            if SellerApplication.objects.filter(
                applicant=request.user,
                status=SellerApplication.Status.PENDING,
            ).exists():
                return Response(
                    {'detail': 'You already have a pending seller application.'},
                    status=status.HTTP_409_CONFLICT,
                )
            raise

        return Response(
            {
                'id': application.pk,
                'status': application.status,
                'detail': 'Seller application submitted.',
            },
            status=status.HTTP_201_CREATED,
        )
        
@ensure_csrf_cookie
def csrf_cookie_view(request):
    return JsonResponse({'csrfToken': get_token(request)})

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request},
        )

        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.check_password(serializer.validated_data['current_password']):
                return Response(
                    {'current_password': 'The current password is incorrect.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(serializer.validated_data['new_password'])
            user.session_version += 1
            user.save(update_fields=['password', 'session_version'])
            update_session_auth_hash(request, user)
            request.session['session-version'] = user.session_version

        audit_logger.log(audit_logger.create_log_entry(LogType.PASSWORD_CHANGE, {
                    'actor': user.pk,
                    'target': user.pk,
                    'result': LogResult.SUCCESS,
                    'reason': 'User changed their password.',
                }))
        send_password_change_notice(user.email)
        
        return Response({'detail': 'Your password has been changed.'})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(email=serializer.validated_data['email']).first()
        if user is not None:
            _, raw_token = PasswordResetToken.issue(user)
            send_password_reset_link(
                user.email,
                f'{settings.PASSWORD_RESET_URL.rstrip("/")}/{raw_token}',
            )

        return Response({
            'detail': 'If an account exists for that email, a password reset link has been sent.'
        })


class PasswordResetView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, token):
        reset_token = PasswordResetToken.resolve(token)
        if reset_token is None or not reset_token.is_valid:
            return Response(
                {'detail': 'This password reset link is invalid or has expired.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = NewPasswordSerializer(data=request.data, context={'user': reset_token.user})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            reset_token = (
                PasswordResetToken.objects
                .select_for_update()
                .select_related('user')
                .get(pk=reset_token.pk)
            )
            if not reset_token.is_valid:
                return Response(
                    {'detail': 'This password reset link is invalid or has expired.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = User.objects.select_for_update().get(pk=reset_token.user_id)
            user.set_password(serializer.validated_data['password'])
            user.session_version += 1
            user.save(update_fields=['password', 'session_version'])
            reset_token.used_at = timezone.now()
            reset_token.save(update_fields=['used_at'])

        send_password_change_notice(user.email)
        audit_logger.log(audit_logger.create_log_entry(LogType.PASSWORD_RESET, {
            'actor': None,
            'target': user.pk,
            'result': LogResult.SUCCESS,
            'reason': 'User reset their password using an email reset link.',
        }))
        return Response({'detail': 'Your password has been reset. Please log in again.'})


LOGIN_CHALLENGE_TTL_SECONDS = 300


def _json_body(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _complete_login(request, user):
    previous_login = (
        LoginHistory.objects.filter(user=user).order_by("-login_time").first()
    )
    request.session.flush()
    login(request, user)
    request.session["session-version"] = user.session_version
    LoginHistory.objects.create(user=user)
    audit_logger.log(audit_logger.create_log_entry(LogType.LOGIN, {
        "actor": user.pk,
        "target": user.pk,
        "result": LogResult.SUCCESS,
        "reason": "User logged in successfully.",
    }))
    return previous_login.login_time if previous_login else None


def _begin_login_challenge(request, user, enrollment_required=False):
    request.session.flush()
    request.session["mfa_pending_user_id"] = user.pk
    request.session["mfa_pending_session_version"] = user.session_version
    request.session["mfa_pending_expires_at"] = int(timezone.now().timestamp()) + LOGIN_CHALLENGE_TTL_SECONDS
    request.session["mfa_pending_type"] = "enrollment" if enrollment_required else "totp"
    request.session.set_expiry(LOGIN_CHALLENGE_TTL_SECONDS)
    return JsonResponse({
        "mfa_required": not enrollment_required,
        "enrollment_required": enrollment_required,
    })


def _pending_login_user(request):
    user_id = request.session.get("mfa_pending_user_id")
    expires_at = request.session.get("mfa_pending_expires_at")
    if not user_id or not expires_at:
        return None
    if timezone.now().timestamp() >= expires_at:
        request.session.flush()
        return None
    user = User.objects.filter(
        pk=user_id, is_active=True, email_verified=True,
        session_version=request.session.get("mfa_pending_session_version"),
    ).first()
    if user is None:
        request.session.flush()
    return user


def _login_limit_response(ip):
    allowed, retry_at = check_login_allowed(ip)
    if allowed:
        return None
    when = date_format(retry_at, "Y-m-d H:i:s")
    return JsonResponse(
        {"error": f"Too many failed log-in attempts. Try again after {when} UTC."},
        status=429,
    )


@csrf_protect
def login_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    ip = get_client_ip(request)
    limited = _login_limit_response(ip)
    if limited:
        return limited

    data = _json_body(request)
    if data is None or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str):
        return JsonResponse({"error": "Email and password are required."}, status=400)
    email = data["email"]
    user = authenticate(request, username=email, password=data["password"])

    if user is None:
        normalized_email = User.objects.normalize_email(email)
        target = User.objects.filter(email=normalized_email).values_list("pk", flat=True).first()
        audit_logger.log(audit_logger.create_log_entry(LogType.LOGIN, {
            "target": target,
            "actor": None,
            "reason": "Failed login attempt with invalid credentials.",
            "result": LogResult.FAILED,
        }))
        record_login_failure(ip)
        return JsonResponse({"error": "Invalid email or password."}, status=401)

    if not user.email_verified:
        audit_logger.log(audit_logger.create_log_entry(LogType.LOGIN, {
            "actor": None,
            "target": user.pk,
            "reason": "Failed login attempt: email address not verified.",
            "result": LogResult.FAILED,
        }))
        return JsonResponse(
            {"error": "Please verify your email address before logging in."},
            status=401,
        )

    if user.totp_enabled:
        return _begin_login_challenge(request, user)
    if is_administrator(user):
        return _begin_login_challenge(request, user, enrollment_required=True)

    previous_login = _complete_login(request, user)
    return JsonResponse({
        "message": "Login successful.",
        "previous_login": previous_login,
    })


@csrf_protect
def login_mfa_verify_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    ip = get_client_ip(request)
    limited = _login_limit_response(ip)
    if limited:
        return limited

    user = _pending_login_user(request)
    if user is None or request.session.get("mfa_pending_type") != "totp":
        return JsonResponse({"error": "Your sign-in challenge has expired. Please log in again."}, status=401)

    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "A verification code is required."}, status=400)

    code = data.get("code")
    recovery_code = data.get("recovery_code")
    if (code is None) == (recovery_code is None):
        return JsonResponse({"error": "Provide either a TOTP code or a recovery code."}, status=400)

    valid = False
    if code is not None:
        try:
            secret = decrypt_totp_secret(user.totp_secret_encrypted)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Two-factor authentication is not configured correctly."}, status=500)
        valid = verify_totp(secret, code)
    elif (
        isinstance(recovery_code, str)
        and len("".join(recovery_code.split())) == 20
        and "".join(recovery_code.split()).isascii()
        and "".join(recovery_code.split()).isalnum()
    ):
        code_hash = hash_recovery_code(recovery_code)
        with transaction.atomic():
            valid = user.two_factor_recovery_codes.filter(
                code_hash=code_hash,
                used_at__isnull=True,
            ).update(used_at=timezone.now()) == 1

    if not valid:
        record_login_failure(ip)
        audit_logger.log(audit_logger.create_log_entry(LogType.LOGIN, {
            "actor": None,
            "target": user.pk,
            "reason": "Failed login attempt: invalid second-factor credential.",
            "result": LogResult.FAILED,
        }))
        return JsonResponse({"error": "Invalid verification code."}, status=401)

    previous_login = _complete_login(request, user)
    return JsonResponse({
        "message": "Login successful.",
        "previous_login": previous_login,
    })


def _two_factor_user(request):
    if request.user.is_authenticated:
        return request.user, False
    user = _pending_login_user(request)
    if (
        user is not None
        and request.session.get("mfa_pending_type") == "enrollment"
        and is_administrator(user)
        and not user.totp_enabled
    ):
        return user, True
    return None, False


@csrf_protect
def two_factor_setup_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, pending_admin = _two_factor_user(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.totp_enabled:
        return JsonResponse({"error": "Two-factor authentication is already enabled."}, status=400)

    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Request must contain a JSON body."}, status=400)
    if not pending_admin:
        password = data.get("password")
        if not isinstance(password, str) or not user.check_password(password):
            return JsonResponse({"error": "Current password is incorrect."}, status=401)

    secret = generate_totp_secret()
    user.totp_secret_encrypted = encrypt_totp_secret(secret)
    user.save(update_fields=["totp_secret_encrypted"])
    return JsonResponse({
        "secret": secret,
        "otpauth_url": provisioning_uri(secret, user.email),
    })


@csrf_protect
def two_factor_confirm_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, pending_admin = _two_factor_user(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.totp_enabled:
        return JsonResponse({"error": "Two-factor authentication is already enabled."}, status=400)

    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Request must contain a JSON body."}, status=400)

    ip = get_client_ip(request)
    limited = _login_limit_response(ip)
    if limited:
        return limited

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if user.totp_enabled or not user.totp_secret_encrypted:
            return JsonResponse({"error": "Start two-factor setup before confirming it."}, status=400)
        try:
            secret = decrypt_totp_secret(user.totp_secret_encrypted)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Two-factor setup could not be read."}, status=500)
        if not verify_totp(secret, data.get("code")):
            record_login_failure(ip)
            return JsonResponse({"error": "Invalid verification code."}, status=400)

        recovery_codes = generate_recovery_codes()
        user.totp_enabled = True
        user.save(update_fields=["totp_enabled"])
        TwoFactorRecoveryCode.objects.bulk_create([
            TwoFactorRecoveryCode(user=user, code_hash=hash_recovery_code(code))
            for code in recovery_codes
        ])

    response_data = {"totp_enabled": True, "recovery_codes": recovery_codes}
    if pending_admin:
        response_data["message"] = "Two-factor authentication enabled. Login successful."
        response_data["previous_login"] = _complete_login(request, user)
    return JsonResponse(response_data)

@csrf_exempt
def logout_view(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed"},
            status=405
        )

    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Not authenticated"},
            status=401
        )

    user = request.user

    # Create audit record
    audit_logger.log(audit_logger.create_log_entry(LogType.LOGOUT, {
        "actor": user.pk,
        "target": user.pk,
        "result": LogResult.SUCCESS,
        "reason": "User logged out.",
    }))

    logout(request)

    return JsonResponse({
        "message": "Logout successful."
    })


class IsModerator(BasePermission):
    def has_permission(self, request, view):
        return(
            request.user.is_authenticated
            and Role.objects.filter(
                name__in=["Moderator", "Administrator"], users=request.user
            ).exists()
        )


class PendingSellerApplicationListView(generics.ListAPIView):
    permission_classes = [IsModerator]
    serializer_class = PendingSellerApplicationSerializer

    def get_queryset(self):
        return (
            SellerApplication.objects
            .filter(status=SellerApplication.Status.PENDING)
            .select_related('applicant')
            .order_by('created_at')
        )


class SellerApplicationApproveView(APIView):
    permission_classes = [IsModerator]

    def post(self, request, pk):
        with transaction.atomic():
            application = get_object_or_404(
                SellerApplication.objects.select_for_update(), pk=pk
            )

            if application.applicant_id == request.user.id:
                return Response(
                    {'detail': 'You cannot review your own application.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if application.status != SellerApplication.Status.PENDING:
                return Response(
                    {'detail': 'Only pending applications can be approved.'},
                    status=status.HTTP_409_CONFLICT,
                )

            application.status = SellerApplication.Status.APPROVED
            application.reviewer = request.user
            application.reviewed_at = timezone.now()
            application.save(
                update_fields=['status', 'reviewer', 'reviewed_at', 'updated_at']
            )

            grant_seller(application.applicant)

            # Create audit record
            audit_logger.log(audit_logger.create_log_entry(LogType.APPLICATION_DECISION, {
                "actor": request.user.pk,
                "target": application.applicant_id,
                "result": LogResult.SUCCESS,
                "reason": f"Application {application.pk} approved.",
            }))

            # Create audit record
            audit_logger.log(audit_logger.create_log_entry(LogType.ROLE_CHANGE, {
                "actor": request.user.pk,
                "target": application.applicant_id,
                "result": LogResult.SUCCESS,
                "reason": f"Seller role granted via application {application.pk}.",
            }))

            return Response({
                'id': application.pk,
                'status': application.status,
                'detail': 'Application approved. The applicant is now a seller.'
            })


class SellerApplicationRejectView(APIView):
    permission_classes = [IsModerator]

    def post(self, request, pk):
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'detail': 'A reason is required to reject an application.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            application = get_object_or_404(
                SellerApplication.objects.select_for_update(), pk=pk
            )

            if application.applicant_id == request.user.id:
                return Response(
                    {'detail': 'You cannot review your own application.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if application.status != SellerApplication.Status.PENDING:
                return Response(
                    {'detail': 'Only pending applications can be rejected.'},
                    status=status.HTTP_409_CONFLICT
                )

            application.status = SellerApplication.Status.REJECTED
            application.reviewer = request.user
            application.reviewed_at = timezone.now()
            application.review_reason = reason
            application.save(update_fields=[
                'status', 'reviewer', 'reviewed_at', 'review_reason', 'updated_at',
            ])

            # Create audit record
            audit_logger.log(audit_logger.create_log_entry(LogType.APPLICATION_DECISION, {
                "actor": request.user.pk,
                "target": application.applicant_id,
                "result": LogResult.SUCCESS,
                "reason": f"Application {application.pk} rejected: {reason}",
            }))

        return Response({
            'id': application.pk,
            'status': application.status,
            'detail': 'Application rejected.'
        })


class MySellerApplicationsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MySellerApplicationSerializer

    def get_queryset(self):
        return SellerApplication.objects.filter(
            applicant=self.request.user
        ).order_by('-created_at', '-id')


class PublicProfileView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicProfileSerializer
    queryset = User.objects.filter(is_active=True)


class MyProfileView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileUpdateSerializer

    def patch(self, request):
        serializer = self.get_serializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MyAccountView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AccountUpdateSerializer

    def patch(self, request):
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AccountPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class AccountSearchView(generics.ListAPIView):
    permission_classes = [IsModerator]
    serializer_class = AdminPanelAccountListSerializer
    pagination_class = AccountPagination

    def get_queryset(self):
        queryset = User.objects.prefetch_related('roles').order_by('email')
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | Q(display_name__icontains=search)
            )
        return queryset


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return(
            request.user.is_authenticated
            and Role.objects.filter(name="Administrator", users=request.user).exists()
        )


class AuditLogPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsAdministrator]
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination
    queryset = AuditLog.objects.order_by('-timestamp', '-id')


def get_or_create_wallet_for_request(request, currency=None):
    """
    Retrieves or establishes a wallet:
    - For authenticated members: user-owned persistent wallet.
    - For anonymous guests: wallet bound to their browser session.
    """
    if request.user.is_authenticated:
        wallet, created = Wallet.objects.get_or_create(
            user=request.user,
            defaults={'currency': currency or 'CAD'}
        )
        return wallet, created
    else:
        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key
        wallet, created = Wallet.objects.get_or_create(
            session_key=session_key,
            defaults={'currency': currency or 'CAD'}
        )
        return wallet, created


class WalletDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated:
            wallet = Wallet.objects.filter(user=request.user).first()
        else:
            session_key = request.session.session_key
            wallet = Wallet.objects.filter(session_key=session_key).first() if session_key else None

        if not wallet:
            return Response(
                {"detail": "Wallet not yet initialized."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = WalletSerializer(wallet)
        data = serializer.data
        if wallet.user is None:
            data['warning'] = "Temporary guest wallet. Closing your browser session will lose access."
        return Response(data, status=status.HTTP_200_OK)


class WalletCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = WalletCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chosen_currency = serializer.validated_data['currency']

        if request.user.is_authenticated:
            if hasattr(request.user, 'wallet') and request.user.wallet is not None:
                return Response(
                    {"error": "Wallet already exists and currency cannot be changed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            wallet = Wallet.objects.create(user=request.user, currency=chosen_currency)
        else:
            if not request.session.session_key:
                request.session.save()
            session_key = request.session.session_key
            if Wallet.objects.filter(session_key=session_key).exists():
                return Response(
                    {"error": "Guest wallet already exists and currency cannot be changed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            wallet = Wallet.objects.create(session_key=session_key, currency=chosen_currency)

        return Response(WalletSerializer(wallet).data, status=status.HTTP_201_CREATED)


class WalletTopUpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            wallet = Wallet.objects.filter(user=request.user).first()
        else:
            session_key = request.session.session_key
            wallet = Wallet.objects.filter(session_key=session_key).first() if session_key else None

        if not wallet:
            return Response(
                {"error": "Please initialize your wallet currency first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = WalletTopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = Decimal(str(serializer.validated_data['amount']))

        with transaction.atomic():
            # Lock the wallet record for atomic update
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.balance += amount
            wallet.save(update_fields=['balance'])

            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=WalletTransaction.TransactionType.TOP_UP,
                amount=amount,
                currency=wallet.currency,
                resulting_balance=wallet.balance,
                reference=f"TOPUP-{int(timezone.now().timestamp())}"
            )

        return Response(WalletSerializer(wallet).data, status=status.HTTP_200_OK)
