from rest_framework import serializers

from notifications.models import Notification
from users.models import DeviceToken


class RegisterDeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(
        choices=DeviceToken.Platform.choices,
        default=DeviceToken.Platform.ANDROID,
    )


class UnregisterDeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ["id", "platform", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "event_type", "title", "body", "data",
            "priority", "app", "status", "created_at", "sent_at",
        ]
        read_only_fields = fields
