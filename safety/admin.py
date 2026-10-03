from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from .models import (
    EmergencyAlert, EmergencyContact, NotificationLog, Profile, SafetyCheckIn, SafetyTip,
)

admin.site.site_header = "Smart Women Safety - Admin"
admin.site.site_title = "Safety Admin"


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class UserAdmin(DjangoUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "last_name", "is_staff", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email")


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ("name", "relationship", "phone", "email", "priority", "user", "created_at")
    list_filter = ("relationship", "priority")
    search_fields = ("name", "phone", "email", "user__username", "user__first_name")


class NotificationLogInline(admin.TabularInline):
    model = NotificationLog
    extra = 0
    readonly_fields = ("contact", "channel", "status", "error_message", "created_at")
    can_delete = False


@admin.register(EmergencyAlert)
class EmergencyAlertAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "alert_type", "status", "latitude", "longitude")
    list_filter = ("alert_type", "status", "created_at")
    search_fields = ("user__username", "user__first_name", "message")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    inlines = [NotificationLogInline]


@admin.register(SafetyCheckIn)
class SafetyCheckInAdmin(admin.ModelAdmin):
    list_display = ("user", "duration", "status", "started_at", "expires_at", "completed")
    list_filter = ("status", "duration", "completed")
    search_fields = ("user__username", "user__first_name")


@admin.register(SafetyTip)
class SafetyTipAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "created_at")
    list_filter = ("category",)
    search_fields = ("title", "description")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "alert", "contact", "channel", "status")
    list_filter = ("channel", "status")
