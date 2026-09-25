from decimal import Decimal

from rest_framework import serializers

from payments.models import (
    DriverBalance,
    LedgerEntry,
    Payment,
    Refund,
)


class GatewaySerializer(serializers.Serializer):
    """وصف بوابة متاحة — يُبنى من `gateway.describe()` لا من نموذج."""

    code = serializers.CharField()
    display_name = serializers.CharField()
    is_online = serializers.BooleanField()
    supports_refund = serializers.BooleanField()
    supported_currencies = serializers.ListField(
        child=serializers.CharField(), allow_empty=True
    )


class PaymentSerializer(serializers.ModelSerializer):
    trip_id = serializers.IntegerField(read_only=True)
    ride_id = serializers.IntegerField(source="trip.ride_id", read_only=True)
    refundable_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "trip_id",
            "ride_id",
            "amount",
            "platform_fee",
            "driver_net",
            "amount_refunded",
            "refundable_amount",
            "currency",
            "gateway_code",
            "status",
            "failure_reason",
            "created_at",
            "paid_at",
        ]
        read_only_fields = fields


class ChargePaymentSerializer(serializers.Serializer):
    """
    `gateway_code` اختياري: إن أُغفل تُستخدم البوابة المثبَّتة على الدفعة.
    تمريره يسمح للزبون بتغيير وسيلة الدفع قبل التحصيل.
    """

    gateway_code = serializers.CharField(
        required=False, allow_blank=True, max_length=40
    )


class RefundRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
        # Decimal لا float: DRF يحذّر من الثاني لسبب وجيه — مقارنة حدّ
        # مالي بعدد عشري ثنائي هي كيف يمرّ مبلغ يجب أن يُرفض.
        min_value=Decimal("0.01"),
        help_text="أُغفله لإعادة كامل المتبقّي.",
    )
    reason = serializers.CharField(max_length=300)


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = [
            "id",
            "payment",
            "amount",
            "currency",
            "reason",
            "status",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "payment",
            "account",
            "account_ref",
            "direction",
            "amount",
            "currency",
            "entry_type",
            "transaction_ref",
            "memo",
            "created_at",
        ]
        read_only_fields = fields


class DriverBalanceSerializer(serializers.ModelSerializer):
    owes_platform = serializers.BooleanField(read_only=True)
    amount_owed_to_platform = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = DriverBalance
        fields = [
            "currency",
            "net_balance",
            "owes_platform",
            "amount_owed_to_platform",
            "lifetime_earned",
            "lifetime_commission",
            "updated_at",
        ]
        read_only_fields = fields
