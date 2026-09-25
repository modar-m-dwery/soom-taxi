"""
ضوابط أمنيّة صغيرة لا مكان طبيعيّ لها في تطبيقٍ بعينه.

- عمر توكن الدخول: توكن DRF لا ينتهي أبدًا افتراضًا. هاتفٌ سُرق أو بيع
  يبقى داخلًا إلى الأبد. نحدّه بعمر (`AUTH_TOKEN_TTL_DAYS`، الصفر يطفئه).
- معقوليّة موقع السائق: إحداثيةٌ خارج الكرة، أو قفزةٌ بسرعة طائرة، إمّا
  عطل GPS أو تطبيق تزييف موقع يضع السائق قرب طلبات ليس قربها. تُرفض
  ولا تُكتب — فلا تفسد المطابقة ولا الأجرة.
- لوحات الإدارة (`/admin/` و`/ops/`) تُقصر على عناوين محدّدة إن ضُبطت
  `ADMIN_ALLOWED_IPS`. خارجها 404 لا 403: لا نؤكّد وجود اللوحة.
"""

import math
from datetime import timedelta

from django.conf import settings
from django.http import Http404
from django.utils import timezone


# ---------------------------------------------------------------------
# عمر التوكن
# ---------------------------------------------------------------------

def token_expired(token, now=None):
    days = int(getattr(settings, "AUTH_TOKEN_TTL_DAYS", 0) or 0)
    if days <= 0 or token is None or getattr(token, "created", None) is None:
        return False
    return (now or timezone.now()) - token.created > timedelta(days=days)


# ---------------------------------------------------------------------
# معقوليّة الموقع
# ---------------------------------------------------------------------

# قفزاتٌ دون هذا تُقبل مهما قصر الزمن: ارتعاش GPS في المدينة يصل مئات
# الأمتار بين نبضتين، ورفضه يُخفي سائقًا حقيقيًّا.
LOCATION_JUMP_TOLERANCE_M = 400


def _haversine_m(lng1, lat1, lng2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def location_rejection(lng, lat, previous=None, now=None):
    """
    سبب رفض الموقع، أو None إن كان معقولًا.

    `previous` = (lng, lat, epoch_seconds) لآخر موقع مقبول على الاتصال نفسه.
    """
    if not (math.isfinite(lng) and math.isfinite(lat)):
        return "not_finite"
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return "out_of_range"
    if lat == 0.0 and lng == 0.0:
        # «جزيرة الصفر»: ما يرسله GPS لم يثبت بعد.
        return "null_island"

    if previous is None or now is None:
        return None

    p_lng, p_lat, p_time = previous
    elapsed = max(now - p_time, 0.001)
    distance = _haversine_m(p_lng, p_lat, lng, lat)
    if distance <= LOCATION_JUMP_TOLERANCE_M:
        return None

    max_kmh = float(getattr(settings, "LOCATION_MAX_PLAUSIBLE_SPEED_KMH", 200))
    if distance / elapsed * 3.6 > max_kmh:
        return "implausible_speed"
    return None


# ---------------------------------------------------------------------
# قصر لوحات الإدارة على عناوين
# ---------------------------------------------------------------------

class AdminIPAllowlistMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed = getattr(settings, "ADMIN_ALLOWED_IPS", None) or []
        if allowed and self._protected(request.path):
            from config.throttling import trusted_client_ip

            if trusted_client_ip(request) not in allowed:
                raise Http404()
        return self.get_response(request)

    @staticmethod
    def _protected(path):
        prefixes = (
            "/" + getattr(settings, "ADMIN_URL", "admin/").lstrip("/"),
            "/ops/",
            "/api/v1/ops/",
        )
        return any(path.startswith(prefix) for prefix in prefixes)
