from django.contrib import admin
from .models import AuditLog, LoginHistory, PasswordResetToken, User, EmailVerification, SellerApplication

# Register your models here.
admin.site.register(LoginHistory)
admin.site.register(PasswordResetToken)
admin.site.register(User)
admin.site.register(EmailVerification)
admin.site.register(SellerApplication)


# Audit records are read-only for everyone, including superusers.
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "action", "result", "actor", "target", "reason")
    list_filter = ("action", "result")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
