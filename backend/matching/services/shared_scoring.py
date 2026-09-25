from abc import ABC, abstractmethod
from math import radians, degrees, sin, cos, sqrt, atan2

from django.conf import settings


class SharedCompatibilityStrategy(ABC):
    name = "base"

    @abstractmethod
    def score(self, host_ride, candidate_ride):
        """يرجع رقم من 0 إلى 100 يمثل درجة التوافق."""
        raise NotImplementedError


def _bearing(a, b):
    lat1, lon1 = radians(a.y), radians(a.x)
    lat2, lon2 = radians(b.y), radians(b.x)
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360


def _haversine_km(a, b):
    lat1, lon1 = radians(a.y), radians(a.x)
    lat2, lon2 = radians(b.y), radians(b.x)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * atan2(sqrt(h), sqrt(1 - h))


def _angle_diff(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


class HeuristicStrategy(SharedCompatibilityStrategy):
    """
    مقياس رخيص وسريع: مسافة نقطة الالتقاط + فرق زاوية الاتجاه + قرب الوجهتين.
    لا يحتاج أي API خارجي — يعتمد فقط على خطوط الطول والعرض.
    """
    name = "heuristic"

    def score(self, host_ride, candidate_ride):
        # نفس نصف القطر الذي فلتر المرشّحين، وإلّا اختلف مقياس الترتيب عن
        # مقياس القبول: مرشّحٌ يمرّ الفلترة ويأخذ درجة صفر بلا سبب مفهوم.
        _area = getattr(host_ride, "service_area", None)
        max_pickup_km = (
            _area.effective_shared_join_radius_km
            if _area is not None
            else settings.MATCHING_SHARED_JOIN_RADIUS_KM
        )
        max_dest_km = settings.MATCHING_SHARED_MAX_DEST_DISTANCE_KM

        pickup_km = _haversine_km(host_ride.pickup, candidate_ride.pickup)
        dest_km = _haversine_km(host_ride.destination, candidate_ride.destination)

        bearing_host = _bearing(host_ride.pickup, host_ride.destination)
        bearing_candidate = _bearing(candidate_ride.pickup, candidate_ride.destination)
        angle = _angle_diff(bearing_host, bearing_candidate)

        pickup_score = max(0.0, 100 - (pickup_km / max_pickup_km) * 100)
        dest_score = max(0.0, 100 - (dest_km / max_dest_km) * 100)
        angle_score = max(0.0, 100 - (angle / 90) * 100)

        return round(
            pickup_score * 0.35 + dest_score * 0.30 + angle_score * 0.35,
            1,
        )


class RoutingEngineStrategy(SharedCompatibilityStrategy):
    """
    نسخة مستقبلية: تستدعي محرك ملاحة حقيقي (OSRM/Google Directions/Mapbox)
    لحساب كلفة الانعراج الفعلية على شبكة الطرق بدل التقريب الهندسي.
    غير مفعّلة الآن — عند التنفيذ فقط بدّل MATCHING_SHARED_STRATEGY.
    """
    name = "routing_engine"

    def score(self, host_ride, candidate_ride):
        raise NotImplementedError(
            "استراتيجية محرك الملاحة غير مفعّلة بعد. "
            "أبقِ MATCHING_SHARED_STRATEGY = 'heuristic' حاليًا."
        )


_STRATEGIES = {
    "heuristic": HeuristicStrategy(),
    "routing_engine": RoutingEngineStrategy(),
}


def get_active_strategy():
    return _STRATEGIES[settings.MATCHING_SHARED_STRATEGY]