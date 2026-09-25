"""Create idempotent mobile-demo identities; safe for development and E2E only."""
import json
from datetime import timedelta

from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from rest_framework.authtoken.models import Token

from drivers.models import (
    REQUIRED_DOCUMENT_TYPES,
    DocumentStatus,
    DriverDocument,
)
from users.models import CustomerProfile, DriverProfile, User, UserRole
from vehicles.models import Vehicle, VehicleType


DEMO_USERS = {
    "customer": "+963990000101",
    "driver": "+963990000102",
    "admin": "+963990000103",
}


class Command(BaseCommand):
    help = "Create idempotent mobile API demo accounts, tokens, areas and an active vehicle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-operational", action="store_true",
            help="Clear operational demo data first. Never use against real customer data.",
        )
        parser.add_argument(
            "--i-understand-reset", action="store_true",
            help="Required together with --reset-operational.",
        )

    def handle(self, *args, **options):
        if options["reset_operational"]:
            if not options["i_understand_reset"]:
                raise CommandError("Add --i-understand-reset to confirm operational cleanup.")
            call_command("reset_operational_data", yes=True)

        call_command("locations_resolve_test")
        call_command("seed_rating_tags")

        customer, _ = User.objects.get_or_create(
            phone=DEMO_USERS["customer"],
            defaults={"role": UserRole.CUSTOMER, "name": "Mobile Demo Customer", "is_verified": True},
        )
        customer.role = UserRole.CUSTOMER
        customer.is_verified = True
        customer.is_active = True
        customer.save(update_fields=["role", "is_verified", "is_active"])
        CustomerProfile.objects.get_or_create(user=customer)

        driver_user, _ = User.objects.get_or_create(
            phone=DEMO_USERS["driver"],
            defaults={"role": UserRole.DRIVER, "name": "Mobile Demo Driver", "is_verified": True},
        )
        driver_user.role = UserRole.DRIVER
        driver_user.is_verified = True
        driver_user.is_active = True
        driver_user.save(update_fields=["role", "is_verified", "is_active"])
        driver, _ = DriverProfile.objects.get_or_create(
            user=driver_user,
            defaults={
                "status": DriverProfile.DriverStatus.ACTIVE,
                "available_seats": 4,
                "current_location": Point(35.9275, 35.3617, srid=4326),
                "last_location_at": timezone.now(),
            },
        )
        driver.status = DriverProfile.DriverStatus.ACTIVE
        driver.available_seats = 4
        driver.current_location = Point(35.9275, 35.3617, srid=4326)
        driver.last_location_at = timezone.now()
        driver.save()
        Vehicle.objects.update_or_create(
            plate_number="MOBILE-DEMO-01",
            defaults={
                "driver": driver, "type_id": "taxi", "make": "Demo",
                "model": "Taxi", "year": 2024, "color": "White", "seats": 4, "active": True,
            },
        )

        admin, _ = User.objects.get_or_create(
            phone=DEMO_USERS["admin"],
            defaults={"role": UserRole.ADMIN, "name": "Mobile Demo Admin", "is_verified": True, "is_staff": True},
        )
        admin.role = UserRole.ADMIN
        admin.is_verified = admin.is_active = admin.is_staff = True
        admin.save(update_fields=["role", "is_verified", "is_active", "is_staff"])

        # -------------------------------------------------------------
        # وثائق السائق — بدونها حساب العرض عاجز عن فعل ما وُصف به
        #
        # `DriverEligibilityService.is_eligible` يشترط أربع وثائق مقبولة
        # وغير منتهية، لا مركبةً فعّالة وحدها. وبدونها يردّ
        # POST /drivers/me/go-online/ بـ400 "Driver is not eligible"،
        # فلا يظهر السائق في المطابقة ولا يقدّم عرضًا — أي أنّ التدفّق
        # الذي يصفه MOBILE_API_GUIDE يتوقّف عند خطوته الثالثة.
        # -------------------------------------------------------------
        expires = timezone.now() + timedelta(days=365)

        for doc_type in REQUIRED_DOCUMENT_TYPES:
            document, created = DriverDocument.objects.get_or_create(
                driver=driver,
                type=doc_type,
                defaults={"status": DocumentStatus.APPROVED},
            )

            if created:
                document.file.save(
                    f"demo-{doc_type}.txt",
                    ContentFile(b"mobile demo placeholder - not a real document"),
                    save=False,
                )

            document.status = DocumentStatus.APPROVED
            document.expires_at = expires
            document.reviewed_by = admin
            document.reviewed_at = timezone.now()
            document.save()

        payload = {"base_url": "/api/v1", "accounts": {}}
        for role, user in (("customer", customer), ("driver", driver_user), ("admin", admin)):
            token, _ = Token.objects.get_or_create(user=user)
            payload["accounts"][role] = {"phone": user.phone, "token": token.key}
        payload["driver_profile_id"] = driver.id
        self.stdout.write(self.style.SUCCESS(json.dumps(payload, ensure_ascii=False, indent=2)))