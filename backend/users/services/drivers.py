from django.db import transaction

from users.models import (
    DriverProfile,
    UserRole,
)


class DriverProfileService:

    @staticmethod
    @transaction.atomic
    def become_driver(user):
        """
        تحويل المستخدم الحالي إلى سائق
        وإنشاء DriverProfile إذا لم يكن موجوداً.
        """

        if user.role == UserRole.ADMIN:
            raise ValueError(
                "Admin user cannot be converted to driver."
            )

        if user.role == UserRole.SUPPORT:
            raise ValueError(
                "Support user cannot be converted to driver."
            )

        # تحويل المستخدم إلى Driver
        if user.role != UserRole.DRIVER:
            user.role = UserRole.DRIVER

            user.save(
                update_fields=[
                    "role",
                ]
            )

        # إنشاء DriverProfile
        profile, created = (
            DriverProfile.objects.get_or_create(
                user=user,
                defaults={
                    "status": (
                        DriverProfile
                        .DriverStatus
                        .PENDING
                    ),
                    "online": False,
                },
            )
        )

        return profile, created


    @staticmethod
    @transaction.atomic
    def get_or_create_profile(user):
        if user.role != UserRole.DRIVER:
            raise ValueError(
                "User is not a driver."
            )

        profile, _ = (
            DriverProfile.objects.get_or_create(
                user=user
            )
        )

        return profile