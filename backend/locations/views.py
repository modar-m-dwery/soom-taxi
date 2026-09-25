"""
نقطة الإعداد — ما يقرأه التطبيق عند الإقلاع.

لماذا كانت غائبة، ولماذا غيابها عيب:

منطقة الخدمة تحمل اثنين وثلاثين إعدادًا يضبطها المشغّل من لوحة الإدارة، وكلّ
واحد منها يُفرَض على الطلبات فعلًا. لكن لم يكن للتطبيق طريقة لقراءة أيٍّ
منها. النتيجة أنّ مبرمج التطبيق كان أمام خيارين، وكلاهما رديء:

  • يُثبّت الأرقام في شيفرته — فتصير لوحة الإدارة زينةً: يغيّر المشغّل مهلة
    الدعوة فيرفض الخادم ما يرسله التطبيق، والمستخدم يقرأ رسالة خطأ لا ذنب
    له فيها، ولا يُصلَح ذلك إلّا بإصدار جديد على المتجر.

  • أو يكتشفها بالتجربة: يرسل قيمة خاطئة ويقرأ الخيارات من نصّ الخطأ.

إعدادٌ لا يصل إلى العميل هو نصف إعداد. هذه النقطة هي النصف الثاني.

القراءة عامّة بلا مصادقة عمدًا: التطبيق يحتاجها قبل تسجيل الدخول ليرسم
شاشة الطلب الأولى. وما فيها ليس سرًّا — درجات خدمة وأنصاف أقطار ومهل يراها
أيّ مستخدم في الواجهة. أمّا ما هو سرّ فعلًا — هامش السائق، اسم الجهة
المنظِّمة، معايرة التقدير الداخلي — فلا يخرج من هنا أصلًا.
"""
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.throttling import TrustedAnonThrottle
from locations.models import ServiceArea, SurgeMode
from locations.serializers import AppConfigSerializer
from locations.services import LocationService


class AppConfigView(APIView):
    """GET /api/v1/config/"""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [TrustedAnonThrottle]

    @extend_schema(
        tags=["Config"],
        operation_id="app_config",
        summary="Client bootstrap configuration",
        description=(
            "Every zone-scoped rule the mobile app needs: allowed ride modes, "
            "vehicle categories, invitation TTL options, search and arrival "
            "radii, presence timeouts and pricing policy. Read it once at "
            "startup and never hardcode any of these values — an operator can "
            "change them from the admin panel and the change takes effect "
            "immediately, with no app release.\n\n"
            "Pass `lat`/`lng` to resolve the caller's zone, or `area` to name "
            "one. With neither, the first active zone is returned and "
            "`resolved_from` says `default`."
        ),
        parameters=[
            OpenApiParameter(
                "lat", float, description="Latitude used to resolve the zone."
            ),
            OpenApiParameter(
                "lng", float, description="Longitude used to resolve the zone."
            ),
            OpenApiParameter(
                "area", str, description="Zone code, e.g. JAB. Overridden by lat/lng."
            ),
        ],
        responses={200: AppConfigSerializer},
    )
    def get(self, request):
        area, resolved_from = self._resolve(request)
        return Response(self._build(area, resolved_from), status=status.HTTP_200_OK)

    # -----------------------------------------------------------------
    # حلّ المنطقة
    # -----------------------------------------------------------------

    @staticmethod
    def _resolve(request):
        """
        الإحداثيات أوّلًا لأنّها الحقيقة: المستخدم في المكان الذي فيه، لا في
        المكان الذي سمّاه. والرمز بعدها لمن يريد استعراض مدينة لا يقف فيها.

        وحين لا يصل شيء نُرجع أوّل منطقة فعّالة بدل 400: تطبيقٌ يفتح قبل أن
        يمنحه المستخدم إذن الموقع يجب أن يرسم شاشةً لا رسالة خطأ. ويقول
        `resolved_from` صراحةً إنّ هذا افتراض، فيعيد العميل السؤال بعد أن
        يحصل على الموقع.
        """
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")

        if lat is not None and lng is not None:
            try:
                area = LocationService.resolve_area(float(lng), float(lat))
            except (TypeError, ValueError):
                area = None
            if area is not None:
                return area, "coordinates"
            # إحداثيات خارج كلّ منطقة: لا نكذب ونعطيه مدينة أخرى.
            return None, "none"

        code = (request.query_params.get("area") or "").strip()
        if code:
            area = next(
                (
                    a
                    for a in LocationService.get_active_service_areas()
                    if a.code.lower() == code.lower()
                ),
                None,
            )
            return (area, "code") if area is not None else (None, "none")

        areas = LocationService.get_active_service_areas()
        if areas:
            return areas[0], "default"

        return None, "none"

    # -----------------------------------------------------------------
    # البناء
    # -----------------------------------------------------------------

    @classmethod
    def _build(cls, area, resolved_from):
        from rides.models import RideMode
        from vehicles.models import VehicleCategory

        categories = [
            {
                "code": c.code,
                "name": c.name,
                "seats": c.seats,
                "sort_order": c.sort_order,
            }
            for c in VehicleCategory.active_for_area(area)
        ]

        from catalog.services import Catalog

        ride_modes = Catalog.ride_modes_for(area, [m.value for m in RideMode])

        if area is None:
            # لا منطقة: نعطي الأشكال والافتراضات العامّة لا فراغًا. تطبيقٌ
            # يقرأ null في كلّ حقل ينهار أو يرسم شاشة بيضاء، وكلاهما أسوأ
            # من أرقام معقولة مع resolved_from صريح يقول إنّها ليست مدينته.
            return cls._envelope(
                services=Catalog.services_for(None),
                features=Catalog.features_for(None),
                trip_categories=Catalog.trip_categories_for(None),
                area_code=None,
                area_name=None,
                country_code=None,
                resolved_from=resolved_from,
                ride_modes=ride_modes,
                invitation_modes=ServiceArea.default_invitation_allowed_modes(),
                categories=categories,
                timings=cls._default_timings(),
                geometry=cls._default_geometry(),
                pricing=cls._default_pricing(),
            )

        return cls._envelope(
            services=Catalog.services_for(area),
            features=Catalog.features_for(area),
            trip_categories=Catalog.trip_categories_for(area),
            area_code=area.code,
            area_name=area.name,
            country_code=area.country_code,
            resolved_from=resolved_from,
            ride_modes=ride_modes,
            invitation_modes=list(area.effective_invitation_modes),
            categories=categories,
            timings={
                "offer_ttl_seconds": area.effective_offer_ttl_seconds,
                "ride_search_window_minutes": (
                    area.effective_ride_search_window_minutes
                ),
                "invitation_ttl_options": list(area.effective_ttl_options),
                "invitation_ttl_default": area.effective_ttl_default,
                "invitation_max_parallel": area.invitation_max_parallel or 1,
                "auto_dispatch_ttl_seconds": area.auto_dispatch_ttl_seconds,
                "auto_dispatch_max_attempts": area.auto_dispatch_max_attempts,
                "cancel_free_window_seconds": area.cancel_free_window_seconds,
                "cancel_driver_late_grace_minutes": (
                    area.cancel_driver_late_grace_minutes
                ),
                "late_cancel_strike_limit": area.late_cancel_strike_limit,
                "invitation_reject_cooldown_seconds": (
                    area.effective_invitation_reject_cooldown_seconds
                ),
                "presence_stale_seconds": area.effective_presence_stale_seconds,
                "presence_fresh_seconds": area.effective_presence_fresh_seconds,
                "location_max_age_seconds": (
                    area.effective_location_max_age_seconds
                ),
            },
            geometry={
                "matching_radius_km": area.effective_instant_radius_km,
                "search_radius_options_km": (
                    area.effective_search_radius_options_km
                    if Catalog.feature_enabled("search_radius", area)
                    else []
                ),
                "marketplace_radius_km": area.effective_marketplace_radius_km,
                "shared_join_radius_km": area.effective_shared_join_radius_km,
                "shared_scheduled_pickup_radius_km": (
                    area.effective_shared_scheduled_pickup_radius_km
                ),
                "shared_scheduled_dest_radius_km": (
                    area.effective_shared_scheduled_dest_radius_km
                ),
                "shared_scheduled_time_window_minutes": (
                    area.effective_shared_scheduled_time_window_minutes
                ),
                "arrival_radius_m": area.effective_arrival_radius_m,
                "dropoff_radius_m": area.effective_dropoff_radius_m,
                "marketplace_cell_precision": area.marketplace_cell_precision,
            },
            pricing={
                "currency_code": area.currency_code,
                "default_policy": area.default_pricing_policy,
                "allowed_policies": list(area.effective_pricing_policies),
                "surge_enabled": area.surge_mode != SurgeMode.DISABLED,
                "surge_max_multiplier": (
                    str(area.surge_max_multiplier)
                    if area.surge_max_multiplier is not None
                    else None
                ),
                "min_fare_absolute": (
                    str(area.min_fare_absolute)
                    if area.min_fare_absolute is not None
                    else None
                ),
                "first_ride_discount_pct": str(area.first_ride_discount_pct),
                "first_ride_discount_cap": (
                    str(area.first_ride_discount_cap)
                    if area.first_ride_discount_cap is not None
                    else None
                ),
                "referral_reward": str(area.referral_reward),
            },
        )

    @staticmethod
    def _envelope(**kwargs):
        return {
            "area_code": kwargs["area_code"],
            "area_name": kwargs["area_name"],
            "country_code": kwargs["country_code"],
            "resolved_from": kwargs["resolved_from"],
            "ride_modes": kwargs["ride_modes"],
            "invitation_allowed_modes": kwargs["invitation_modes"],
            "vehicle_categories": kwargs["categories"],
            "services": kwargs["services"],
            "features": kwargs["features"],
            "trip_categories": kwargs["trip_categories"],
            "timings": kwargs["timings"],
            "geometry": kwargs["geometry"],
            "pricing": kwargs["pricing"],
            "server_time": timezone.now(),
        }

    # -----------------------------------------------------------------
    # الافتراضات حين لا تُحلّ منطقة
    #
    # تُقرأ من الإعدادات لا من أرقام مكرّرة هنا: نسختان من الافتراض تتباعدان
    # عند أوّل تغيير، وحينها يعمل الخادم برقم ويعِد التطبيقَ برقم آخر.
    # -----------------------------------------------------------------

    @staticmethod
    def _default_timings():
        from django.conf import settings

        ttl_options = ServiceArea.default_invitation_ttl_options()

        return {
            "offer_ttl_seconds": getattr(settings, "RIDE_OFFER_TTL_SECONDS", 90),
            "ride_search_window_minutes": getattr(
                settings, "RIDE_SEARCH_WINDOW_MINUTES", 10
            ),
            "invitation_ttl_options": ttl_options,
            "invitation_ttl_default": ttl_options[0],
            "invitation_max_parallel": 1,
            "auto_dispatch_ttl_seconds": 15,
            "auto_dispatch_max_attempts": 5,
            "cancel_free_window_seconds": 120,
            "cancel_driver_late_grace_minutes": 5,
            "late_cancel_strike_limit": 3,
            "invitation_reject_cooldown_seconds": getattr(
                settings, "RIDE_INVITATION_REJECT_COOLDOWN_SECONDS", 60
            ),
            "presence_stale_seconds": getattr(
                settings, "PRESENCE_HEARTBEAT_STALE_SECONDS", 60
            ),
            "presence_fresh_seconds": getattr(
                settings, "PRESENCE_HEARTBEAT_FRESH_SECONDS", 30
            ),
            "location_max_age_seconds": getattr(
                settings, "MATCHING_LOCATION_MAX_AGE_SECONDS", 60
            ),
        }

    @staticmethod
    def _default_geometry():
        from django.conf import settings

        return {
            "matching_radius_km": float(
                getattr(settings, "MATCHING_NORMAL_RADIUS_KM", 5)
            ),
            "search_radius_options_km": [],
            "marketplace_radius_km": float(
                getattr(settings, "MATCHING_MARKETPLACE_RADIUS_KM", 10)
            ),
            "shared_join_radius_km": float(
                getattr(settings, "MATCHING_SHARED_JOIN_RADIUS_KM", 3)
            ),
            "shared_scheduled_pickup_radius_km": float(
                getattr(settings, "MATCHING_SHARED_SCHEDULED_PICKUP_RADIUS_KM", 10)
            ),
            "shared_scheduled_dest_radius_km": float(
                getattr(settings, "MATCHING_SHARED_SCHEDULED_DEST_RADIUS_KM", 15)
            ),
            "shared_scheduled_time_window_minutes": int(
                getattr(settings, "MATCHING_SHARED_SCHEDULED_TIME_WINDOW_MINUTES", 60)
            ),
            "arrival_radius_m": getattr(settings, "TRIP_ARRIVAL_RADIUS_M", 200),
            "dropoff_radius_m": getattr(settings, "TRIP_DROPOFF_RADIUS_M", 300),
            "marketplace_cell_precision": 5,
        }

    @staticmethod
    def _default_pricing():
        return {
            "currency_code": "SYP",
            "default_policy": "platform_fixed",
            "allowed_policies": list(ServiceArea.default_pricing_policies()),
            "surge_enabled": False,
            "surge_max_multiplier": None,
            "min_fare_absolute": None,
            "first_ride_discount_pct": "0",
            "first_ride_discount_cap": None,
            "referral_reward": "0",
        }
