from django.contrib import admin, messages
from django.contrib.gis.admin import GISModelAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction
from django.contrib.gis import admin
from django.contrib.gis.db import models
from django.contrib.gis.forms import OSMWidget

from .models import (
    User,
    CustomerProfile,
    DriverProfile,
    DeviceToken,
    OTPChallenge,
    UserRole,
)

from drivers.services.availability import (
    DriverAvailabilityService,
)


class CustomerProfileInline(admin.StackedInline):
    model = CustomerProfile
    extra = 0
    can_delete = False


class DriverProfileInline(admin.StackedInline):
    model = DriverProfile
    fk_name = "user"
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-created_at"]

    list_display = (
        "id",
        "phone",
        "name",
        "role",
        "is_verified",
        "is_active",
        "is_staff",
        "created_at",
    )

    list_filter = (
        "role",
        "is_verified",
        "is_active",
        "is_staff",
    )

    search_fields = (
        "phone",
        "name",
    )

    readonly_fields = (
        "last_login",
        "created_at",
    )

    fieldsets = (
        (
            "User",
            {
                "fields": (
                    "phone",
                    "password",
                    "name",
                    "gender",
                    "role",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "is_verified",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "last_login",
                    "created_at",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            "Create User",
            {
                "classes": ("wide",),
                "fields": (
                    "phone",
                    "password1",
                    "password2",
                    "name",
                    "role",
                    "is_verified",
                    "is_active",
                    "is_staff",
                ),
            },
        ),
    )

    actions = [
        "promote_to_driver",
        "demote_to_customer",
        "verify_users",
        "unverify_users",
        "activate_users",
        "deactivate_users",
    ]

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []

        inlines = []

        if hasattr(obj, "customer_profile"):
            inlines.append(
                CustomerProfileInline(self.model, self.admin_site)
            )

        if hasattr(obj, "driver_profile"):
            inlines.append(
                DriverProfileInline(self.model, self.admin_site)
            )

        return inlines

    @admin.action(description="Convert selected customers to drivers")
    def promote_to_driver(self, request, queryset):
        count = 0

        with transaction.atomic():
            for user in queryset.select_for_update():

                if user.role == UserRole.DRIVER:
                    continue

                DriverProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "status": DriverProfile.DriverStatus.PENDING,
                        "online": False,
                    },
                )

                user.role = UserRole.DRIVER
                user.save(update_fields=["role"])

                count += 1

        self.message_user(
            request,
            f"{count} user(s) converted to driver.",
            messages.SUCCESS,
        )

    @admin.action(description="Convert selected drivers to customers")
    def demote_to_customer(self, request, queryset):
        count = 0

        with transaction.atomic():
            for user in queryset.select_for_update():

                if user.role != UserRole.DRIVER:
                    continue

                user.role = UserRole.CUSTOMER
                user.save(update_fields=["role"])

                CustomerProfile.objects.get_or_create(
                    user=user
                )

                driver = getattr(user, "driver_profile", None)

                if driver:
                    driver.online = False
                    driver.save(update_fields=["online"])

                count += 1

        self.message_user(
            request,
            f"{count} user(s) converted to customer.",
            messages.SUCCESS,
        )

    @admin.action(description="Verify selected users")
    def verify_users(self, request, queryset):
        queryset.update(is_verified=True)

    @admin.action(description="Unverify selected users")
    def unverify_users(self, request, queryset):
        queryset.update(is_verified=False)

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
    )

    search_fields = (
        "user__phone",
        "user__name",
    )


@admin.register(DriverProfile)
class DriverProfileAdmin(GISModelAdmin):
    formfield_overrides = {
        models.PointField: {
            "widget": OSMWidget(
                attrs={
                    "map_width": 800,
                    "map_height": 500,
                }
            )
        },
    }
    list_display = (
        "id",
        "user",
        "status",
        "online",
        "rating",
        "current_occupancy",
        "available_seats",
        "last_location_at",
        "verified_at",
    )

    list_filter = (
        "status",
        "online",
    )

    search_fields = (
        "user__phone",
        "user__name",
    )

    readonly_fields = (
        "remaining_seats",
        "verified_at",
    )

    fieldsets = (
        (
            "Driver",
            {
                "fields": (
                    "user",
                    "status",
                    "rating",
                    "verification_note",
                )
            },
        ),
        (
            "Availability",
            {
                "fields": (
                    "online",
                    "current_occupancy",
                    "available_seats",
                    "remaining_seats",
                )
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "current_location",
                    "last_location_at",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "verified_by",
                    "verified_at",
                )
            },
        ),
    )

    actions = [
        "activate_drivers",
        "suspend_drivers",
        "set_online",
        "set_offline",
    ]

    @admin.action(description="Activate selected drivers")
    def activate_drivers(self, request, queryset):
        queryset.update(
            status=DriverProfile.DriverStatus.ACTIVE
        )

    @admin.action(description="Suspend selected drivers")
    def suspend_drivers(self, request, queryset):
        queryset.update(
            status=DriverProfile.DriverStatus.SUSPENDED,
            online=False,
        )

    @admin.action(description="Set selected drivers ONLINE")
    def set_online(self, request, queryset):
        updated = 0

        for driver in queryset:
            try:
                DriverAvailabilityService.go_online(driver)
                updated += 1
            except ValueError:
                continue

        self.message_user(
            request,
            f"{updated} driver(s) set online.",
            messages.SUCCESS,
        )

    @admin.action(description="Set selected drivers OFFLINE")
    def set_offline(self, request, queryset):
        queryset.update(online=False)


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "platform",
        "is_active",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "platform",
        "is_active",
    )

    search_fields = (
        "user__phone",
        "token",
    )


@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "phone",
        "attempts",
        "max_attempts",
        "expires_at",
        "consumed_at",
        "created_at",
    )

    list_filter = (
        "consumed_at",
    )

    search_fields = (
        "phone",
    )

    readonly_fields = (
        "code_hash",
        "created_at",
    )