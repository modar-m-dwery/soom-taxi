"""
السؤال الوحيد الذي تطرحه بقيّة الشيفرة: هل هذه الخدمة/الميزة شغّالة هنا؟

قراءةٌ واحدة من القاعدة لكلّ الجداول الأربعة، مخزَّنة في الكاش حتّى يحفظ
المشغّل تغييرًا (catalog/signals.py يمسحها) — فالسؤال يُطرح في كلّ طلب رحلة
بلا استعلام.
"""

from django.core.cache import cache

from catalog.registry import FEATURES, SERVICES, ServiceStatus

CACHE_KEY = "catalog:state:v1"
CACHE_TTL_SECONDS = 300


class ServiceUnavailable(Exception):
    """الخدمة أو الميزة مطفأة هنا. رسالتها تُعرض للمستخدم كما هي."""


def _state():
    state = cache.get(CACHE_KEY)
    if state is not None:
        return state

    from catalog.models import FeatureFlag, FeatureFlagAreaOverride, Service, ServiceAreaOverride

    state = {
        "services": {
            s.code: {
                "code": s.code, "name": s.name, "name_en": s.name_en,
                "icon": s.icon, "description": s.description,
                "status": s.status, "sort_order": s.sort_order,
            }
            for s in Service.objects.all()
        },
        "service_overrides": {
            (o.service.code, o.area_id): o.status
            for o in ServiceAreaOverride.objects.select_related("service")
        },
        "features": {f.key: f.enabled for f in FeatureFlag.objects.all()},
        "feature_overrides": {
            (o.flag.key, o.area_id): o.enabled
            for o in FeatureFlagAreaOverride.objects.select_related("flag")
        },
    }
    cache.set(CACHE_KEY, state, CACHE_TTL_SECONDS)
    return state


def invalidate():
    cache.delete(CACHE_KEY)


def _area_id(area):
    return getattr(area, "id", None)


class Catalog:

    @staticmethod
    def service_status(code, area=None):
        state = _state()
        override = state["service_overrides"].get((code, _area_id(area)))
        if override is not None:
            return override
        row = state["services"].get(code)
        if row is not None:
            return row["status"]
        definition = SERVICES.get(code)
        # خدمةٌ عُرِّفت ولم تُزامَن بعد: افتراضها. غير معرَّفة أصلًا: مخفيّة.
        return definition.default_status if definition else ServiceStatus.HIDDEN

    @classmethod
    def service_active(cls, code, area=None):
        return cls.service_status(code, area) == ServiceStatus.ACTIVE

    @staticmethod
    def feature_enabled(key, area=None):
        state = _state()
        override = state["feature_overrides"].get((key, _area_id(area)))
        if override is not None:
            return override
        if key in state["features"]:
            return state["features"][key]
        definition = FEATURES.get(key)
        return definition.default if definition else False

    @classmethod
    def services_for(cls, area=None):
        """ما يراه التطبيق: الخدمات غير المخفيّة، مرتّبة، بحالتها في المدينة."""
        state = _state()
        rows = []
        for code, row in state["services"].items():
            status = cls.service_status(code, area)
            if status == ServiceStatus.HIDDEN:
                continue
            rows.append({**row, "status": status})
        rows.sort(key=lambda r: (r["sort_order"], r["code"]))
        return rows

    @classmethod
    def features_for(cls, area=None):
        keys = set(FEATURES) | set(_state()["features"])
        return {key: cls.feature_enabled(key, area) for key in sorted(keys)}

    # ------------------------------------------------------------------
    # الفرض
    # ------------------------------------------------------------------

    @classmethod
    def require_service(cls, code, area=None):
        if not cls.service_active(code, area):
            definition = SERVICES.get(code)
            name = definition.name if definition else code
            raise ServiceUnavailable(f"خدمة «{name}» غير متاحة حاليًّا.")

    @classmethod
    def require_feature(cls, key, area=None, message=None):
        if not cls.feature_enabled(key, area):
            raise ServiceUnavailable(message or "هذه الميزة متوقّفة حاليًّا.")

    @classmethod
    def ride_modes_for(cls, area, all_modes):
        """الأنماط بعد إسقاط ما أُطفئت خدمته (المشترك اليوم)."""
        blocked = {
            d.ride_mode for d in SERVICES.values()
            if d.ride_mode and not cls.service_active(d.code, area)
        }
        return [m for m in all_modes if m not in blocked]

    @classmethod
    def trip_categories_for(cls, area):
        categories = ["city"]
        for d in SERVICES.values():
            if d.trip_category and cls.service_active(d.code, area):
                categories.append(d.trip_category)
        return categories

    @classmethod
    def service_for_mode(cls, mode):
        return next((d.code for d in SERVICES.values() if d.ride_mode == mode), None)

    @classmethod
    def service_for_category(cls, category):
        return next(
            (d.code for d in SERVICES.values() if d.trip_category == category), None
        )
