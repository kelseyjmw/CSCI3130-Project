from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from log.audit_logger import Logger, LogResult, LogType

from .models import Role
from .permissions import HasPermission

audit_logger = Logger()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return

User = get_user_model()

ROLE_NAMES = ["Buyer", "Seller", "Moderator", "Administrator"]


def user_roles(user):
    return list(user.roles.values_list("name", flat=True))


class ProtectedView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "items.buy"

    def get(self, request):
        return Response({"ok": True})


class UserListView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "accounts.change_roles"

    def get(self, request):
        rows = []
        for user in User.objects.order_by("email"):
            rows.append({
                "id": user.id,
                "email": user.email,
                "email_verified": user.email_verified,
                "roles": user_roles(user),
            })
        return Response(rows)


class UserRolesView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "accounts.change_roles"

    def put(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

        names = request.data.get("roles")
        if not isinstance(names, list):
            return Response({"error": "roles must be a list."}, status=400)

        wanted = set()
        for name in names:
            if name not in ROLE_NAMES:
                return Response({"error": "Invalid role."}, status=400)
            wanted.add(name)

        current = {role.name: role for role in user.roles.all()}
        try:
            for name, role in current.items():
                if name not in wanted:
                    role.users.remove(user)
            for name in wanted:
                if name not in current:
                    role, _ = Role.objects.get_or_create(name=name)
                    role.users.add(user)
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return Response({"error": msg}, status=400)

        return Response({
            "id": user.id,
            "email": user.email,
            "roles": user_roles(user),
        })


def account_row(user):
    return {
        "id": user.id,
        "email": user.email,
        "roles": user_roles(user),
        "account_state": user.account_state,
        "suspension_reason": user.suspension_reason,
        "state_changed_at": user.state_changed_at,
        "suspended_at": user.suspended_at,
    }


class AccountStateListView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "accounts.suspend"

    def get(self, request):
        rows = []
        for user in User.objects.order_by("email"):
            rows.append(account_row(user))
        return Response(rows)


class AccountStateView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "accounts.suspend"

    def put(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

        state = request.data.get("account_state")
        reason = request.data.get("reason")
        if state not in ("Active", "Suspended"):
            return Response({"error": "account_state must be Active or Suspended."}, status=400)
        if not isinstance(reason, str) or not reason.strip():
            return Response({"error": "A reason is required."}, status=400)

        now = timezone.now()
        user.account_state = state
        user.state_changed_at = now
        if state == "Suspended":
            user.suspension_reason = reason.strip()
            user.suspended_at = now
        else:
            user.suspension_reason = ""
            user.suspended_at = None

        try:
            user.save(update_fields=[
                "account_state",
                "suspension_reason",
                "state_changed_at",
                "suspended_at",
            ])
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            audit_logger.log(audit_logger.create_log_entry(LogType.ACCOUNT_STATE, {
                "actor": request.user.pk,
                "target": user.pk,
                "result": LogResult.FAILED,
                "reason": reason.strip(),
            }))
            return Response({"error": msg}, status=400)

        audit_logger.log(audit_logger.create_log_entry(LogType.ACCOUNT_STATE, {
            "actor": request.user.pk,
            "target": user.pk,
            "result": LogResult.SUCCESS,
            "reason": reason.strip(),
        }))
        return Response(account_row(user))
