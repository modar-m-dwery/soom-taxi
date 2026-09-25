"""
حرّاس نقاط النهاية: خدمةٌ أو ميزةٌ مطفأة تردّ 403 برسالة واضحة.

إخفاء الزرّ في التطبيق لا يكفي: نسخةٌ قديمة من التطبيق، أو أحدٌ ينادي
الـAPI مباشرةً، يصل إلى ما أطفأه المشغّل. الخادم هو الحَكَم.

النقاط التي لا تعرف مدينة الطلب تُحكَم بالحالة العامّة؛ واستثناءات المدن
تُفرض حيث المدينة معروفة (إنشاء الطلب، /config/).
"""

from rest_framework.permissions import BasePermission

from catalog.registry import FEATURES, SERVICES
from catalog.services import Catalog


def requires_service(code):
    definition = SERVICES.get(code)
    name = definition.name if definition else code

    class _ServiceActive(BasePermission):
        message = f"خدمة «{name}» غير متاحة حاليًّا."

        def has_permission(self, request, view):
            return Catalog.service_active(code)

    _ServiceActive.__name__ = f"ServiceActive_{code}"
    return _ServiceActive


def requires_feature(key):
    definition = FEATURES.get(key)

    class _FeatureEnabled(BasePermission):
        message = (
            f"{definition.description} — متوقّفة حاليًّا."
            if definition else "هذه الميزة متوقّفة حاليًّا."
        )

        def has_permission(self, request, view):
            return Catalog.feature_enabled(key)

    _FeatureEnabled.__name__ = f"FeatureEnabled_{key}"
    return _FeatureEnabled
