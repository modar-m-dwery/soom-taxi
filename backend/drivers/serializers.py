import os

from django.conf import settings

from rest_framework import serializers

from drivers.models import (
    DriverDocument,
    DocumentType,
)


#: صيغ وثائق السائق المقبولة. قائمة بيضاء لا سوداء: القائمة السوداء
#: تُنسى امتداداتُها الجديدة، والبيضاء تُخطئ في اتجاه الرفض.
ALLOWED_DOCUMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".heic"}

ALLOWED_DOCUMENT_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic",
    "application/pdf",
}

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024  # ٨ ميغابايت: صورة رخصة لا فيلم


class SubmitDocumentSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=DocumentType.choices,
    )

    file = serializers.FileField()

    expires_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )

    def validate_file(self, value):
        """
        يمنع رفع ما ليس وثيقة.

        الخطر ليس نظريًّا: `FileField()` عارية تقبل أيّ شيء، والملفّ
        يُخزَّن تحت `MEDIA_ROOT` الذي يُخدَم من نفس الأصل. ملفّ `.html`
        أو `.svg` مرفوعٌ هناك يصير سكربتًا يعمل على أصل واجهة الإدارة
        وSwagger — أي XSS مخزَّن على أصلنا نحن.

        ثلاثة فحوص لأنّ أيًّا منها وحده يُخدع: الامتداد يُزوَّر بإعادة
        التسمية، ونوع المحتوى يرسله العميل، والحجم لا يقول شيئًا عن
        النوع. مجتمعةً ترفع كلفة الالتفاف كثيرًا.
        """
        name = (getattr(value, "name", "") or "").strip()
        extension = os.path.splitext(name)[1].lower()

        if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise serializers.ValidationError(
                "صيغة غير مقبولة. المسموح: "
                + "، ".join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))
            )

        content_type = (getattr(value, "content_type", "") or "").lower()
        if content_type and content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"نوع محتوى غير مقبول: {content_type}"
            )

        size = getattr(value, "size", 0) or 0
        limit = getattr(settings, "MAX_DOCUMENT_BYTES", MAX_DOCUMENT_BYTES)

        if size > limit:
            raise serializers.ValidationError(
                f"الملفّ أكبر من الحدّ ({limit // (1024 * 1024)} ميغابايت)."
            )

        if size == 0:
            raise serializers.ValidationError("الملفّ فارغ.")

        return value


class DriverDocumentSerializer(
    serializers.ModelSerializer
):
    # لا نُخرج مسار /media/ الخامّ: كان يشير إلى ملفّ يُخدَم بلا مصادقة.
    # هذا الرابط يمرّ بفحص الملكية في DriverDocumentFileView.
    file_url = serializers.SerializerMethodField()

    def get_file_url(self, obj) -> str | None:
        if not obj.file:
            return None
        return f"/api/v1/drivers/documents/{obj.pk}/file/"

    class Meta:
        model = DriverDocument

        fields = [
            "id",
            "type",
            "file_url",
            "status",
            "expires_at",
            "rejection_reason",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class ReviewDocumentSerializer(serializers.Serializer):
    approve = serializers.BooleanField()

    rejection_reason = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )

    def validate(self, attrs):
        approve = attrs.get("approve")
        rejection_reason = attrs.get(
            "rejection_reason",
            "",
        ).strip()

        if not approve and not rejection_reason:
            raise serializers.ValidationError(
                {
                    "rejection_reason": (
                        "This field is required when "
                        "rejecting a document."
                    )
                }
            )

        attrs["rejection_reason"] = rejection_reason

        return attrs


class VerifyDriverSerializer(serializers.Serializer):
    approve = serializers.BooleanField()

    verification_note = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
    )

    def validate(self, attrs):
        note = attrs.get(
            "verification_note",
            "",
        ).strip()

        if not attrs["approve"] and not note:
            raise serializers.ValidationError(
                {
                    "verification_note": (
                        "This field is required when "
                        "rejecting a driver."
                    )
                }
            )

        attrs["verification_note"] = note

        return attrs


class DriverAdminSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField(
        read_only=True,
    )

    user_id = serializers.IntegerField(
        source="user.id",
        read_only=True,
    )

    phone = serializers.CharField(
        source="user.phone",
        read_only=True,
    )

    name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    role = serializers.CharField(
        source="user.role",
        read_only=True,
    )

    status = serializers.CharField(
        read_only=True,
    )

    rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )

    online = serializers.BooleanField(
        read_only=True,
    )

    current_occupancy = serializers.IntegerField(
        read_only=True,
    )

    available_seats = serializers.IntegerField(
        read_only=True,
    )

    verification_note = serializers.CharField(
        read_only=True,
    )

    verified_at = serializers.DateTimeField(
        read_only=True,
    )