"""
طبقة التوجيه — مزوّد خارجي مع تقدير داخلي يحلّ محلّه عند العطل.

المشكلة التي يحلّها هذا الملفّ
------------------------------
النسخة السابقة كانت تستدعي المزوّد بلا شرط وتحوّل أيّ إخفاق إلى خطأ
تحقّق. عمليًا: انقطاع المزوّد يعني أنّ **أحدًا لا يستطيع حجز رحلة**.
والمزوّد الحالي خادم OSRM تجريبي عامّ بلا عقد خدمة.

وكان في `settings.py` مفتاحان — `MAPS_ROUTING_ENABLED` و
`MAPS_ROUTING_REQUIRED` — لا يقرأهما أيّ سطر في المشروع. اسمهما يَعِد
بسلوك لم يكن موجودًا. هنا صارا يعملان فعلًا:

    ENABLED=False   → لا نسأل المزوّد إطلاقًا، تقدير داخلي دائمًا
    REQUIRED=True   → إخفاق المزوّد يوقف الطلب (السلوك القديم)
    REQUIRED=False  → إخفاق المزوّد يتراجع إلى التقدير الداخلي

ثلاثة قرارات تستحقّ التفسير
---------------------------
**١. التقدير ليس المسافة الهوائية.** خطّ مستقيم بين نقطتين في مدينة
ساحلية يُقصّر المسافة الحقيقية بالثلث تقريبًا. نضرب بمعامل التفاف
(`road_detour_factor`) قابل للمعايرة لكلّ منطقة خدمة، لأنّ شبكة شوارع
جبلة ليست شبكة دمشق.

**٢. قاطع دورة (circuit breaker).** بدونه، انقطاع المزوّد يعني أنّ كلّ
طلب ينتظر عشر ثوانٍ قبل أن يفشل. مع خمسمئة سائق يعمل النظام على مهلة
الشبكة لا على منطقه. بعد ثلاثة إخفاقات متتالية نتوقّف عن السؤال ستّين
ثانية، ثمّ نحاول مرّة واحدة (نصف مفتوح).

**٣. النتيجة تحمل مصدرها.** كلّ استجابة فيها `source`، وهي تُحفظ على
الرحلة. سعرٌ بُني على تقدير يجب أن يكون مميَّزًا في التدقيق المالي عن
سعرٍ بُني على مسار حقيقي — وإلّا صار الفرق شكوى بلا جواب.
"""
from __future__ import annotations

import logging
import math
import threading
import time

from django.conf import settings

import requests


logger = logging.getLogger(__name__)


class RoutingError(Exception):
    """يُرمى فقط حين يكون المسار الحقيقي إلزاميًا ولم نحصل عليه."""


# مصادر النتيجة — تُحفظ على الرحلة وتظهر في الاستجابة
SOURCE_PROVIDER = "provider"
SOURCE_ESTIMATED = "estimated"


# ---------------------------------------------------------------
# قاطع الدورة
# ---------------------------------------------------------------


class _CircuitBreaker:
    """
    ثلاث حالات: مغلق (نسأل)، مفتوح (لا نسأل)، نصف مفتوح (محاولة واحدة).

    الحالة في الذاكرة لا في Redis عمدًا: كلّ عملية daphne/celery تراقب
    المزوّد من موقعها، وعطلٌ يراه عاملٌ واحد لا يعني بالضرورة أنّ الآخر
    يراه. ومزامنتها عبر الشبكة تضيف اعتمادًا جديدًا لحماية اعتماد قائم.
    """

    def __init__(self, threshold: int, cooldown_seconds: int):
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def allows_request(self) -> bool:
        with self._lock:
            if self._failures < self._threshold:
                return True

            if time.monotonic() - self._opened_at >= self._cooldown:
                # نصف مفتوح: نسمح بمحاولة واحدة تحسم الأمر
                self._failures = self._threshold - 1
                return True

            return False

    def record_success(self) -> None:
        with self._lock:
            if self._failures:
                logger.info("routing: عاد المزوّد — أُغلق القاطع.")
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures == self._threshold:
                self._opened_at = time.monotonic()
                logger.warning(
                    "routing: فُتح القاطع بعد %s إخفاقًا — تقدير داخلي "
                    "لمدّة %s ثانية.",
                    self._threshold,
                    self._cooldown,
                )

    def snapshot(self) -> dict:
        with self._lock:
            is_open = self._failures >= self._threshold and (
                time.monotonic() - self._opened_at < self._cooldown
            )
            return {
                "state": "open" if is_open else "closed",
                "consecutive_failures": self._failures,
            }


_breaker = _CircuitBreaker(
    threshold=getattr(settings, "MAPS_ROUTING_BREAKER_THRESHOLD", 3),
    cooldown_seconds=getattr(settings, "MAPS_ROUTING_BREAKER_COOLDOWN", 60),
)


# ---------------------------------------------------------------
# التقدير الداخلي
# ---------------------------------------------------------------

_EARTH_RADIUS_KM = 6371.0088


def haversine_km(lng1, lat1, lng2, lat2) -> float:
    """المسافة الهوائية بالكيلومترات بين نقطتين جغرافيّتين."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    )

    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _area_value(service_area, field, default):
    value = getattr(service_area, field, None) if service_area else None
    return float(value) if value is not None else float(default)


def estimate_route(pickup, destination, service_area=None) -> dict:
    """
    تقديرٌ لا يحتاج شبكة: مسافة هوائية × معامل التفاف، وزمنٌ من سرعة وسطية.

    ليس بديلًا عن مسار حقيقي، لكنّه أفضل بكثير من رفض الطلب — ونحن
    نُعلِّم النتيجة بمصدرها فلا يختلط الأمر على أحد لاحقًا.
    """
    straight_km = haversine_km(
        pickup.x, pickup.y, destination.x, destination.y
    )

    detour = _area_value(
        service_area,
        "road_detour_factor",
        getattr(settings, "MAPS_ROAD_DETOUR_FACTOR", 1.35),
    )

    speed_kmh = _area_value(
        service_area,
        "average_speed_kmh",
        getattr(settings, "MAPS_AVERAGE_SPEED_KMH", 30),
    )

    distance_km = round(straight_km * detour, 2)

    # حدّ أدنى دقيقة واحدة: رحلة داخل الحيّ ليست صفر دقيقة
    duration_minutes = max(round((distance_km / max(speed_kmh, 1)) * 60), 1)

    return {
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
        # لا هندسة مسار: خطّ مستقيم على الخريطة كذبٌ بصريّ أسوأ من لا شيء
        "geometry": None,
        "legs": [],
        "waypoints": [],
        "source": SOURCE_ESTIMATED,
        "straight_line_km": round(straight_km, 2),
        "detour_factor": detour,
    }


# ---------------------------------------------------------------
# الخدمة
# ---------------------------------------------------------------


class RoutingService:

    # خطّاف تجاوز للاختبارات: سكربتات قديمة تضبط RoutingService.BASE_URL
    # مباشرةً لتصنع عطلًا مصطنعًا. إبقاؤه يكلّف سطرين ويمنع كسرها.
    BASE_URL: str | None = None

    @classmethod
    def base_url(cls) -> str:
        return (
            cls.BASE_URL
            or getattr(
                settings,
                "MAPS_ROUTING_BASE_URL",
                "https://router.project-osrm.org",
            )
        ).rstrip("/")

    # -----------------------------------------------------------
    # الواجهة العامّة
    # -----------------------------------------------------------

    @classmethod
    def route(cls, pickup, destination, service_area=None) -> dict:
        """
        pickup / destination: كائنات Point من GEOS (x=خط الطول، y=العرض).

        تُعيد قاموسًا فيه distance_km وduration_minutes وgeometry وsource.
        لا ترمي إلّا حين يكون المسار الحقيقي إلزاميًا وتعذّر الحصول عليه.
        """
        enabled = getattr(settings, "MAPS_ROUTING_ENABLED", True)
        required = getattr(settings, "MAPS_ROUTING_REQUIRED", False)

        if not enabled:
            return estimate_route(pickup, destination, service_area)

        if not _breaker.allows_request():
            if required:
                raise RoutingError(
                    "Routing provider is unavailable (circuit open)."
                )
            logger.debug("routing: القاطع مفتوح — تقدير داخلي.")
            return estimate_route(pickup, destination, service_area)

        try:
            result = cls._call_provider(pickup, destination)

        except RoutingError as exc:
            _breaker.record_failure()

            if required:
                raise

            logger.warning(
                "routing: تعذّر المزوّد (%s) — تقدير داخلي بدلًا منه.", exc
            )
            return estimate_route(pickup, destination, service_area)

        _breaker.record_success()
        return result

    @classmethod
    def health(cls) -> dict:
        """حالة المزوّد للوحة التشغيل — بلا استدعاء شبكة."""
        return {
            "enabled": getattr(settings, "MAPS_ROUTING_ENABLED", True),
            "required": getattr(settings, "MAPS_ROUTING_REQUIRED", False),
            "base_url": cls.base_url(),
            **_breaker.snapshot(),
        }

    # -----------------------------------------------------------
    # المزوّد
    # -----------------------------------------------------------

    @classmethod
    def _call_provider(cls, pickup, destination) -> dict:
        coordinates = (
            f"{pickup.x},{pickup.y};" f"{destination.x},{destination.y}"
        )

        url = f"{cls.base_url()}/route/v1/driving/{coordinates}"

        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
            "alternatives": "false",
        }

        headers = {
            "User-Agent": getattr(
                settings, "MAPS_USER_AGENT", "SoumTaxi/1.0"
            ),
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=getattr(settings, "MAPS_ROUTING_TIMEOUT_SECONDS", 10),
            )
        except requests.RequestException as exc:
            raise RoutingError("Routing provider is unavailable.") from exc

        if response.status_code != 200:
            raise RoutingError(
                f"Routing provider returned HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RoutingError(
                "Routing provider returned invalid JSON."
            ) from exc

        if data.get("code") != "Ok":
            raise RoutingError(data.get("message", "No route found."))

        routes = data.get("routes") or []
        if not routes:
            raise RoutingError("No route found.")

        route = routes[0]
        distance_meters = route.get("distance")
        duration_seconds = route.get("duration")

        if distance_meters is None:
            raise RoutingError("Routing response has no distance.")
        if duration_seconds is None:
            raise RoutingError("Routing response has no duration.")

        return {
            "distance_km": round(distance_meters / 1000, 2),
            "duration_minutes": max(round(duration_seconds / 60), 1),
            "geometry": route.get("geometry"),
            "legs": route.get("legs", []),
            "waypoints": data.get("waypoints", []),
            "source": SOURCE_PROVIDER,
        }
