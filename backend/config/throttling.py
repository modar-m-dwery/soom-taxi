"""
حدود المعدّل — مُفعَّلة فعلًا هذه المرّة.

ما كان الوضع
------------
`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` كان معرَّفًا بمعدّلين، وبلا
`DEFAULT_THROTTLE_CLASSES`. وهذا يعني أنّ DRF **لا يخنق شيئًا إطلاقًا**:
المعدّلات جدولُ أسعار بلا صرّاف. الواجهة الوحيدة التي كانت مخنوقة فعلًا
هي `maps/views.py` لأنّها تُعلن `throttle_classes` بنفسها.

وهذا أسوأ من غياب الإعداد: إعدادٌ موجود يوحي بأنّ المسألة محسومة.

المبدأ هنا
----------
حدٌّ عامّ لكلّ مستخدم، وحدود مشدّدة على ثلاث فئات تُسيء بطبيعتها:

  otp_request   إصدار رموز — يكلّف مالًا حقيقيًّا لكلّ رسالة
  otp_verify    تخمين الرموز — يمنح توكن مصادقة عند النجاح
  write         كتابة تُنشئ صفوفًا وتستدعي مزوّدًا خارجيًّا

الهوية عند عدم المصادقة
-----------------------
DRF يستعمل `REMOTE_ADDR` أو `X-Forwarded-For` بلا تمييز. خلف Nginx تكون
الترويسة مسلسلة `client, proxy1, proxy2`، وأوّل عنصر فيها **يرسله
العميل**. أخذُ الأوّل يعني أنّ الخانق يُهزَم بترويسة واحدة مزوّرة.
`TrustedClientIPMixin` يعدّ من **الآخر** بمقدار `TRUSTED_PROXY_COUNT`،
وهو العدد الحقيقي الوحيد الذي لا يستطيع العميل التأثير فيه.
"""
from django.conf import settings

from rest_framework.throttling import (
    AnonRateThrottle,
    ScopedRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


def trusted_client_ip(request) -> str:
    """
    عنوان العميل الذي لا يستطيع العميل تزويره.

    `X-Forwarded-For` يُقرأ من اليمين: كلّ وسيط يُلحق العنوان الذي رآه.
    فآخر `TRUSTED_PROXY_COUNT` عنصرًا كتبتها وسطاؤنا، والعنصر الذي
    يسبقها مباشرةً هو أوّل عنوان لم يكتبه العميل بنفسه.

    بلا وسطاء (TRUSTED_PROXY_COUNT=0) نتجاهل الترويسة كلّها ونأخذ
    `REMOTE_ADDR` — وهو الصحيح تمامًا حين لا يوجد وسيط.
    """
    depth = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0))
    remote = request.META.get("REMOTE_ADDR", "") or "unknown"

    if depth <= 0:
        return remote

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not forwarded:
        return remote

    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not chain:
        return remote

    index = len(chain) - depth
    if index < 0:
        # سلسلة أقصر من المتوقّع: إمّا سوء إعداد وإمّا محاولة تلاعب.
        # نأخذ الأبعد الذي نثق به بدل أن نصدّق ما أرسله العميل.
        return chain[0]

    return chain[index]


class TrustedClientIPMixin:
    def get_ident(self, request):
        if request.user and request.user.is_authenticated:
            return f"user:{request.user.pk}"
        return trusted_client_ip(request)


class TrustedAnonThrottle(TrustedClientIPMixin, AnonRateThrottle):
    """خانق المجهولين، بعنوان لا يُزوَّر."""


class TrustedUserThrottle(TrustedClientIPMixin, UserRateThrottle):
    """الحدّ العامّ لكلّ مستخدم مصادَق."""


class TrustedScopedThrottle(TrustedClientIPMixin, ScopedRateThrottle):
    """خانق بنطاق مُعلَن على الـview عبر `throttle_scope`."""


class OTPRequestThrottle(TrustedClientIPMixin, SimpleRateThrottle):
    """
    خانق طلب الرمز على مستوى الشبكة.

    طبقة ثانية فوق `RateLimitService` لا بديلٌ عنها: تلك تحدّ بالهاتف
    والجهاز والـIP في Redis وتُعيد 429 برسالة مفهومة، وهذه تقف قبلها
    فتمنع حتى الوصول إلى القاعدة. مهاجمٌ يدوّر أرقام الهواتف يتجاوز حدّ
    الهاتف بسهولة — ولا يتجاوز هذا.
    """

    scope = "otp_request"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": trusted_client_ip(request),
        }


class OTPVerifyThrottle(TrustedClientIPMixin, SimpleRateThrottle):
    """
    خانق تحقّق الرمز.

    كان غائبًا تمامًا: `VerifyOTPView` بلا مصادقة ولا صلاحيات ولا خانق
    ولا حتّى نداء لـ`RateLimitService` — والفرامل الوحيدة كانت خمس
    محاولات لكلّ تحدٍّ. وهي نقطة **تُصدر توكن مصادقة** عند النجاح، على
    فضاء من ستّ خانات.
    """

    scope = "otp_verify"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": trusted_client_ip(request),
        }


class WriteThrottle(TrustedClientIPMixin, SimpleRateThrottle):
    """
    حدّ على الكتابات المكلفة: إنشاء طلب رحلة، تقديم عرض، حجز مقعد.

    كلّ واحدة منها تُنشئ صفوفًا وتستدعي التسعير، وبعضها يستدعي مزوّد
    خرائط خارجيًّا. بلا حدّ، حسابٌ واحد يستنزف حصّة المزوّد ويملأ القاعدة.
    """

    scope = "write"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None  # القراءة يحكمها الحدّ العامّ
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
