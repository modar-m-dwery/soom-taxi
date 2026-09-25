"""مُسلسِلات سجلّ التدقيق — قراءة فقط، إدارة فقط."""
from rest_framework import serializers

from ops.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_phone = serializers.CharField(
        source="actor_user.phone", read_only=True, default=None
    )

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "entity_type",
            "entity_id",
            "action",
            "from_state",
            "to_state",
            "actor_label",
            "actor_role",
            "actor_phone",
            "reason",
            "metadata",
            "request_id",
            "created_at",
        ]
        read_only_fields = fields
