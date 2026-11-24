from django.contrib import admin

from .models import LoginFailure, Permission, Role


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    filter_horizontal = ("permissions", "users")


admin.site.register(Permission)
admin.site.register(LoginFailure)
