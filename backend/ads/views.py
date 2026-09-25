from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from ads.models import Ad, Placement
from catalog.permissions import requires_feature
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from locations.models import ServiceArea


class AdSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Ad
        fields = ["id", "title", "placement", "image_url", "link_url", "service_code"]

    def get_image_url(self, obj) -> str:
        return f"/api/v1/ads/{obj.id}/image/"


def _live(placement, area):
    now = timezone.now()
    ads = (
        Ad.objects.filter(is_active=True, placement=placement)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
    )
    if area is not None:
        ads = ads.filter(Q(areas__isnull=True) | Q(areas=area)).distinct()
    else:
        ads = ads.filter(areas__isnull=True)
    return ads


class AdsListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, requires_feature("ads")]

    @extend_schema(
        tags=["Ads"],
        operation_id="list_ads",
        parameters=[
            OpenApiParameter("placement", str, required=True, enum=[p.value for p in Placement]),
            OpenApiParameter("area", str, required=False),
        ],
        responses={200: AdSerializer(many=True)},
    )
    def get(self, request):
        placement = request.query_params.get("placement")
        if placement not in Placement.values:
            return Response({"detail": "placement غير معروف."}, status=status.HTTP_400_BAD_REQUEST)
        area = ServiceArea.objects.filter(code=request.query_params.get("area") or "").first()
        ads = list(_live(placement, area)[:5])
        return Response(AdSerializer(ads, many=True).data)


class AdEventSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["impression", "click"])


class AdEventThrottle(UserRateThrottle):
    # عدّادٌ يُنفخ بنداءات آليّة يكذب على المعلِن.
    rate = "120/hour"


class AdEventView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AdEventThrottle]

    @extend_schema(tags=["Ads"], operation_id="ad_event", request=AdEventSerializer, responses={204: None})
    def post(self, request, ad_id):
        serializer = AdEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ad = Ad.objects.filter(pk=ad_id, is_active=True).first()
        if ad is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ad.count(serializer.validated_data["kind"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdImageView(APIView):
    """الصورة عبر نقطةٍ بعينها لا مجلّد media كاملًا مكشوفًا."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(tags=["Ads"], operation_id="ad_image", responses={200: bytes})
    def get(self, request, ad_id):
        ad = Ad.objects.filter(pk=ad_id, is_active=True).first()
        if ad is None or not ad.image:
            raise Http404()
        response = FileResponse(ad.image.open("rb"))
        response["Cache-Control"] = "public, max-age=86400"
        response["X-Content-Type-Options"] = "nosniff"
        return response
