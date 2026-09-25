from django.db import models
from django.utils import timezone

from users.models import DriverProfile


class DocumentType(models.TextChoices):
    NATIONAL_ID = "national_id", "National ID"
    DRIVER_LICENSE = "driver_license", "Driver License"
    VEHICLE_REGISTRATION = (
        "vehicle_registration",
        "Vehicle Registration",
    )
    VEHICLE_INSURANCE = (
        "vehicle_insurance",
        "Vehicle Insurance",
    )


class DocumentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


REQUIRED_DOCUMENT_TYPES = [
    DocumentType.NATIONAL_ID,
    DocumentType.DRIVER_LICENSE,
    DocumentType.VEHICLE_REGISTRATION,
    DocumentType.VEHICLE_INSURANCE,
]


class DriverDocument(models.Model):
    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
    )

    file = models.FileField(
        upload_to="driver_documents/%Y/%m/",
    )

    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.PENDING,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rejection_reason = models.CharField(
        max_length=255,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_documents",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["driver", "type"],
            ),
            models.Index(
                fields=["status"],
            ),
        ]

    @property
    def is_expired(self):
        return (
            self.expires_at is not None
            and timezone.now() >= self.expires_at
        )

    @property
    def is_valid_for_eligibility(self):
        return (
            self.status == DocumentStatus.APPROVED
            and not self.is_expired
        )

    def __str__(self):
        return f"DriverDocument({self.driver_id}, {self.type})"