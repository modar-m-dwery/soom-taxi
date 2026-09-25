"""
مزامنة السجلّ مع القاعدة بعد كلّ ترحيل: ينشئ ما نقص، ولا يمسّ ما وُجد.

خدمةٌ أطفأها المشغّل أو غيّر اسمها تبقى كما تركها — الشيفرة لا تغلب قراره.
"""


def sync_definitions(sender=None, **kwargs):
    from catalog.models import FeatureFlag, Service
    from catalog.registry import FEATURES, SERVICES
    from catalog.services import invalidate

    for definition in SERVICES.values():
        Service.objects.get_or_create(
            code=definition.code,
            defaults={
                "name": definition.name,
                "name_en": definition.name_en,
                "icon": definition.icon,
                "description": definition.description,
                "status": definition.default_status,
                "sort_order": definition.sort_order,
            },
        )

    for definition in FEATURES.values():
        FeatureFlag.objects.get_or_create(
            key=definition.key,
            defaults={
                "description": definition.description,
                "enabled": definition.default,
            },
        )

    invalidate()
