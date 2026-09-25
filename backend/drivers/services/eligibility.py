from django.db import transaction
from django.utils import timezone

from drivers.models import (
    DriverDocument,
    DocumentStatus,
    REQUIRED_DOCUMENT_TYPES,
)
from users.models import DriverProfile
from vehicles.models import Vehicle


class DriverEligibilityService:

    @staticmethod
    @transaction.atomic
    def submit_document(
        driver_profile,
        doc_type,
        file,
        expires_at=None,
    ):
        """
        تسجيل وثيقة جديدة للسائق.

        الوثيقة الجديدة تبدأ دائمًا بحالة PENDING.
        """

        document = DriverDocument.objects.create(
            driver=driver_profile,
            type=doc_type,
            file=file,
            expires_at=expires_at,
            status=DocumentStatus.PENDING,
        )

        # إذا كان السائق ACTIVE ثم رفع وثيقة جديدة،
        # فلا نبقيه جاهزًا للمطابقة حتى تتم مراجعة الوثيقة الجديدة.
        if driver_profile.status == DriverProfile.DriverStatus.ACTIVE:
            driver_profile.status = DriverProfile.DriverStatus.PENDING
            driver_profile.online = False
            driver_profile.verification_note = (
                "Driver verification is pending after a new document submission."
            )

            driver_profile.save(
                update_fields=[
                    "status",
                    "online",
                    "verification_note",
                ]
            )

        return document

    @staticmethod
    @transaction.atomic
    def review_document(
        document_id,
        admin_user,
        approve,
        rejection_reason="",
    ):
        """
        قبول أو رفض وثيقة واحدة.
        """

        document = (
            DriverDocument.objects
            .select_for_update()
            .select_related("driver")
            .get(id=document_id)
        )

        if approve:
            document.status = DocumentStatus.APPROVED
            document.rejection_reason = ""
        else:
            document.status = DocumentStatus.REJECTED
            document.rejection_reason = rejection_reason

        document.reviewed_by = admin_user
        document.reviewed_at = timezone.now()

        document.save(
            update_fields=[
                "status",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
            ]
        )

        # لا نقوم بتفعيل السائق تلقائيًا هنا.
        #
        # السبب:
        # قبول وثيقة واحدة لا يعني أن السائق أصبح مؤهلًا.
        #
        # القرار النهائي يتم عبر verify_driver().
        return document

    @staticmethod
    def _latest_documents_by_type(driver_profile):
        """
        إرجاع أحدث وثيقة من كل نوع.
        """

        documents = (
            DriverDocument.objects
            .filter(driver=driver_profile)
            .order_by(
                "type",
                "-created_at",
            )
        )

        latest = {}

        for document in documents:
            if document.type not in latest:
                latest[document.type] = document

        return latest

    @classmethod
    def is_eligible(cls, driver_profile):
        """
        السائق مؤهل إذا:

        1. لديه مركبة فعالة.
        2. جميع الوثائق المطلوبة موجودة.
        3. أحدث نسخة من كل وثيقة APPROVED.
        4. الوثائق غير منتهية.
        """

        active_vehicle_exists = Vehicle.objects.filter(
            driver=driver_profile,
            active=True,
        ).exists()

        if not active_vehicle_exists:
            return False

        latest_documents = cls._latest_documents_by_type(
            driver_profile
        )

        for required_type in REQUIRED_DOCUMENT_TYPES:
            document = latest_documents.get(required_type)

            if document is None:
                return False

            if not document.is_valid_for_eligibility:
                return False

        return True

    @classmethod
    @transaction.atomic
    def verify_driver(
        cls,
        driver_profile,
        admin_user,
        approve=True,
        verification_note="",
    ):
        """
        القرار النهائي للإدارة بشأن السائق.

        approve=True:
            يصبح السائق ACTIVE إذا كان مستوفيًا لكل الشروط.

        approve=False:
            يصبح REJECTED ولا يدخل المطابقة.
        """

        driver_profile = (
            DriverProfile.objects
            .select_for_update()
            .get(id=driver_profile.id)
        )

        if not approve:
            driver_profile.status = (
                DriverProfile.DriverStatus.REJECTED
            )

            driver_profile.online = False
            driver_profile.verification_note = (
                verification_note
            )
            driver_profile.verified_by = admin_user
            driver_profile.verified_at = timezone.now()

            driver_profile.save(
                update_fields=[
                    "status",
                    "online",
                    "verification_note",
                    "verified_by",
                    "verified_at",
                ]
            )

            return driver_profile

        if not cls.is_eligible(driver_profile):
            raise ValueError(
                "Driver is not eligible for activation."
            )

        active_vehicle = (
            Vehicle.objects
            .filter(
                driver=driver_profile,
                active=True,
            )
            .order_by("-created_at")
            .first()
        )

        driver_profile.status = (
            DriverProfile.DriverStatus.ACTIVE
        )

        driver_profile.online = False

        driver_profile.available_seats = (
            active_vehicle.seats
        )

        driver_profile.verification_note = (
            verification_note
        )

        driver_profile.verified_by = admin_user
        driver_profile.verified_at = timezone.now()

        driver_profile.save(
            update_fields=[
                "status",
                "online",
                "available_seats",
                "verification_note",
                "verified_by",
                "verified_at",
            ]
        )

        return driver_profile

    @classmethod
    @transaction.atomic
    def activate_driver(cls, driver_profile):
        """
        تفعيل داخلي للسائق إذا كان مستوفيًا للشروط.

        هذه الدالة مفيدة للخدمات الداخلية،
        لكن القرار الإداري النهائي يفضل أن يمر عبر verify_driver().
        """

        driver_profile = (
            DriverProfile.objects
            .select_for_update()
            .get(id=driver_profile.id)
        )

        if not cls.is_eligible(driver_profile):
            return driver_profile

        active_vehicle = (
            Vehicle.objects
            .filter(
                driver=driver_profile,
                active=True,
            )
            .order_by("-created_at")
            .first()
        )

        driver_profile.status = (
            DriverProfile.DriverStatus.ACTIVE
        )

        driver_profile.available_seats = (
            active_vehicle.seats
        )

        driver_profile.save(
            update_fields=[
                "status",
                "available_seats",
            ]
        )

        return driver_profile

    @classmethod
    def is_ready_for_matching(cls, driver_profile):
        """
        الشرط النهائي لدخول السائق في المطابقة.

        ACTIVE
        + ONLINE
        + Eligible
        + Active Vehicle
        """

        if (
            driver_profile.status
            != DriverProfile.DriverStatus.ACTIVE
        ):
            return False

        if not driver_profile.online:
            return False

        return cls.is_eligible(driver_profile)

    @staticmethod
    @transaction.atomic
    def suspend_driver(
        driver_profile,
        admin_user,
        reason="",
    ):
        """
        إيقاف سائق كان فعالًا.
        """

        driver_profile = (
            DriverProfile.objects
            .select_for_update()
            .get(id=driver_profile.id)
        )

        driver_profile.status = (
            DriverProfile.DriverStatus.SUSPENDED
        )

        driver_profile.online = False
        driver_profile.verification_note = reason
        driver_profile.verified_by = admin_user
        driver_profile.verified_at = timezone.now()

        driver_profile.save(
            update_fields=[
                "status",
                "online",
                "verification_note",
                "verified_by",
                "verified_at",
            ]
        )

        return driver_profile