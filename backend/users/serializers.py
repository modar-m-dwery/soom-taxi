from rest_framework import serializers
from users.models import User


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
        min_length=8,
        trim_whitespace=True,
    )

    device_id = serializers.CharField(
        max_length=255,
        min_length=1,
        trim_whitespace=True,
    )

    code = serializers.CharField(
        max_length=6,
        min_length=6,
        trim_whitespace=True,
    )

    def validate_phone(self, value):
        value = value.strip()

        if not value.startswith("+"):
            raise serializers.ValidationError(
                "Phone number must include the country code."
            )

        digits = value[1:]

        if not digits.isdigit():
            raise serializers.ValidationError(
                "Phone number must contain digits only after the + sign."
            )

        return value

    def validate_code(self, value):
        value = value.strip()

        if not value.isdigit():
            raise serializers.ValidationError(
                "OTP code must contain digits only."
            )

        return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "name",
            "role",
            "is_verified",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields


class RequestOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
        min_length=8,
        trim_whitespace=True,
    )

    device_id = serializers.CharField(
        max_length=255,
        min_length=1,
        trim_whitespace=True,
    )

    def validate_phone(self, value):
        value = value.strip()

        if not value.startswith("+"):
            raise serializers.ValidationError(
                "Phone number must include the country code."
            )

        digits = value[1:]

        if not digits.isdigit():
            raise serializers.ValidationError(
                "Phone number must contain digits only after the + sign."
            )

        return value