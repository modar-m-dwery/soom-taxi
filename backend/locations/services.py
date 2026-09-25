"""
LocationService: يحل "أي منطقة خدمة تقع فيها هذه النقطة؟" ثم يبني area_id
لغرف الماركت بليس، ويُرجع سياق التسعير الخاص بتلك المنطقة.

كل ما يخص "قواعد هذا البلد" يمرّ من هنا — لا يوجد في المشروع مكان آخر
يعرف أن جبلة تختلف عن عمّان.
"""
from math import radians, sin, cos, sqrt, atan2

from django.contrib.gis.geos import Point
from django.core.cache import cache

from locations.geohash import encode as geohash_encode

CACHE_KEY = "locations:service_areas:active"
CACHE_TTL_SECONDS = 300  # احتياطي فقط - الإبطال الفعلي فوري عبر signal


class LocationService:

    @staticmethod
    def _haversine_km(lng1, lat1, lng2, lat2):
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lng1, lat2, lng2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return 6371.0 * 2 * atan2(sqrt(h), sqrt(1 - h))

    # -----------------------------------------------------------
    # CACHE
    # -----------------------------------------------------------

    @classmethod
    def get_active_service_areas(cls):
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        from locations.models import ServiceArea

        areas = list(ServiceArea.objects.filter(is_active=True))
        cache.set(CACHE_KEY, areas, CACHE_TTL_SECONDS)
        return areas

    @classmethod
    def invalidate_cache(cls):
        cache.delete(CACHE_KEY)

    # -----------------------------------------------------------
    # RESOLUTION
    # -----------------------------------------------------------

    @classmethod
    def resolve_area(cls, lng, lat):
        """
        يرجّع ServiceArea التي تحوي هذه النقطة، أو None لو كانت خارج كل
        مناطق الخدمة المُفعَّلة حاليًا.
        """
        point = Point(lng, lat, srid=4326)

        for area in cls.get_active_service_areas():
            if area.boundary is not None:
                if area.boundary.contains(point):
                    return area
                continue  # لها حدود دقيقة وهذه النقطة خارجها - جرّب التالية

            if area.center is not None:
                distance_km = cls._haversine_km(lng, lat, area.center.x, area.center.y)
                if distance_km <= float(area.fallback_radius_km):
                    return area

        return None

    @classmethod
    def resolve_area_for_ride(cls, ride):
        """
        منطقة الرحلة = منطقة نقطة الالتقاط، لا الوجهة. السبب: القواعد
        التنظيمية تتبع مكان بدء الخدمة، ورحلة من جبلة إلى اللاذقية تخضع
        لقواعد جبلة لا لقواعد الوجهة.
        """
        if ride is None or ride.pickup is None:
            return None
        return cls.resolve_area(ride.pickup.x, ride.pickup.y)

    @classmethod
    def compute_marketplace_cell_id(cls, lng, lat):
        """
        نقطة الدخول التي يستخدمها الجزء G. يرجّع "{area_code}:{geohash}"
        مثل "JAB:sy390vj"، أو None خارج مناطق الخدمة.
        """
        area = cls.resolve_area(lng, lat)

        if area is None:
            return None

        cell = geohash_encode(lng, lat, precision=area.marketplace_cell_precision)
        return f"{area.code}:{cell}"

    # -----------------------------------------------------------
    # الوجهة المُقرَّبة للرحلات المشتركة (المرحلة 8)
    # -----------------------------------------------------------

    @classmethod
    def coarse_destination_cell(cls, lng, lat, area=None):
        """
        وجهة الركّاب الحاليين كما تُعرض لمرشّح الانضمام: خليّة geohash خشنة
        بدل إحداثيات دقيقة. الدقّة يقرّرها الأدمن لكل مدينة ضمن حدود
        SharedDestinationPrecision (4 إلى 6 فقط).

        هذا ما يسمح للفلترة بأن تتم دون كشف عنوان أحد.
        """
        area = area or cls.resolve_area(lng, lat)

        precision = getattr(area, "shared_destination_precision", None) or 5
        precision = max(4, min(int(precision), 6))

        return geohash_encode(lng, lat, precision=precision)

    # -----------------------------------------------------------
    # سياق التسعير
    # -----------------------------------------------------------

    @classmethod
    def get_pricing_context(cls, ride=None, lng=None, lat=None):
        """
        يرجّع dict جاهزًا لتمريره إلى PricingService.quote().
        يعمل مع رحلة كاملة أو مع إحداثيات مجرّدة (للتقديرات قبل إنشاء الطلب).

        عند عدم وجود منطقة خدمة مطابقة: نرجّع منطقة None، ما يعني
        "بلا قيود إضافية" — وهو السلوك الحالي قبل هذه الطبقة، أي لا انكسار.
        """
        if ride is not None:
            area = cls.resolve_area_for_ride(ride)
        elif lng is not None and lat is not None:
            area = cls.resolve_area(lng, lat)
        else:
            area = None

        return {
            "service_area": area,
            "policy": area.default_pricing_policy if area else None,
            "currency": area.currency_code if area else None,
        }
