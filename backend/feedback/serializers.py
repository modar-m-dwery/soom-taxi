from rest_framework import serializers

from feedback.models import (
    Complaint,
    ComplaintCategory,
    Rating,
    RatingSummary,
    RatingTag,
)


class RatingTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = RatingTag
        fields = ["code", "label", "direction", "polarity", "min_score", "max_score"]


class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rating
        fields = [
            "id", "direction", "score", "tags", "comment", "created_at",
        ]
        read_only_fields = fields


class SubmitRatingSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=1, max_value=5)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40),
        required=False,
        allow_empty=True,
    )
    comment = serializers.CharField(
        required=False, allow_blank=True, max_length=2000
    )


class TripRatingStateSerializer(serializers.Serializer):
    """
    حالة التقييم كما يراها طرف واحد. theirs يبقى null حتى ينكشف - الحجب
    يتم بعدم الإرسال لا بعلَم في الحمولة.
    """
    direction = serializers.CharField()
    can_rate = serializers.BooleanField()
    theirs_visible = serializers.BooleanField()
    mine = RatingSerializer(allow_null=True)
    theirs = RatingSerializer(allow_null=True)


class RatingSummarySerializer(serializers.ModelSerializer):
    distribution = serializers.SerializerMethodField()

    class Meta:
        model = RatingSummary
        fields = ["average", "count", "distribution", "recalculated_at"]

    def get_distribution(self, obj) -> dict:
        return {
            "1": obj.one_star,
            "2": obj.two_star,
            "3": obj.three_star,
            "4": obj.four_star,
            "5": obj.five_star,
        }


class ComplaintSerializer(serializers.ModelSerializer):
    ride_id = serializers.IntegerField(source="trip.ride_id", read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id", "ride_id", "category", "severity", "status",
            "description", "resolution_note", "resolved_at", "created_at",
        ]
        read_only_fields = fields


class ComplaintDetailSerializer(ComplaintSerializer):
    class Meta(ComplaintSerializer.Meta):
        fields = ComplaintSerializer.Meta.fields + ["evidence"]
        read_only_fields = fields


class OpenComplaintSerializer(serializers.Serializer):
    ride_id = serializers.IntegerField()
    category = serializers.ChoiceField(choices=ComplaintCategory.choices)
    description = serializers.CharField(max_length=5000)
