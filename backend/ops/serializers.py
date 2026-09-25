from rest_framework import serializers

from ops.models import AdminAction


class AdminActionSerializer(serializers.ModelSerializer):
    actor_phone = serializers.CharField(source="actor.phone", read_only=True)

    class Meta:
        model = AdminAction
        fields = [
            "id", "kind", "actor", "actor_phone", "target_type", "target_id",
            "reason", "before", "after", "created_at",
        ]
        read_only_fields = fields


class ReasonSerializer(serializers.Serializer):
    """
    السبب إلزامي في كل تدخّل. الحدّ الأدنى مفروض في الخدمة أيضًا لا هنا
    فقط: أي مسار آخر يصل إليها (أمر إداري، سكربت) يجب أن يخضع للقاعدة
    نفسها.
    """
    reason = serializers.CharField(min_length=10, max_length=2000)


class DriverStatusSerializer(ReasonSerializer):
    status = serializers.ChoiceField(choices=["active", "rejected", "suspended"])
