# -*- coding: utf-8 -*-
"""
لوحة التشغيل — صفحة واحدة تُخدَم من الخادم نفسه.

الجمهور الثالث في وثيقة المنتج («لوحة ويب: يراقب الأسطول حيًّا، يحلّ
العوالق، يوثّق السائقين، يقرأ المؤشّرات وسجلّ التدقيق»). لا بناء ولا
حزم: HTML واحد يتكلّم مع نقاط /ops/ و/drivers/admin/ الموجودة وبثّ
/ws/admin/live/ — بالمفتاح نفسه الذي يستعمله التطبيق، فلا صلاحيات ثانية.
"""

from django.views.generic import TemplateView


class OpsConsoleView(TemplateView):
    template_name = "ops/dashboard.html"
