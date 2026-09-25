from rest_framework import serializers

from vehicles.fields import VehicleCategoryField
from vehicles.models import Vehicle


class VehicleSerializer(
    serializers.ModelSerializer
):
    # يبقى الردّ نصًّا ("sedan") كما كان قبل تحويل العمود إلى مفتاح أجنبي:
    # عقد الـAPI لم يتغيّر بحرف، والتغيير كلّه تحت السطح.
    type = VehicleCategoryField(read_only=True)

    class Meta:
        model = Vehicle

        fields = [
            "id",
            "type",
            "make",
            "model",
            "year",
            "color",
            "plate_number",
            "seats",
            "active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "active",
            "created_at",
            "updated_at",
        ]


class RegisterVehicleSerializer(
    serializers.Serializer
):
    type = VehicleCategoryField()

    make = serializers.CharField(
        max_length=100
    )

    model = serializers.CharField(
        max_length=100
    )

    year = serializers.IntegerField(
        min_value=1990,
        max_value=2100,
    )

    color = serializers.CharField(
        max_length=50
    )

    plate_number = serializers.CharField(
        max_length=20
    )

    seats = serializers.IntegerField(
        min_value=1,
        max_value=8,
    )

    def validate_make(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Make cannot be empty."
            )

        return value

    def validate_model(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Model cannot be empty."
            )

        return value

    def validate_color(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Color cannot be empty."
            )

        return value

    def validate_plate_number(self, value):
        value = value.strip().upper()

        if not value:
            raise serializers.ValidationError(
                "Plate number cannot be empty."
            )

        if Vehicle.objects.filter(
            plate_number=value
        ).exists():
            raise serializers.ValidationError(
                "This plate number is already registered."
            )

        return value