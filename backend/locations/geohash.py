"""
ترميز geohash بسيط (encode فقط - decode غير مطلوب حاليًا) بدون أي
اعتمادية خارجية. تعمدت عدم استخدام مكتبة مثل python-geohash لأنها
C-extension وقد تسبب مشاكل تثبيت على Windows (بيئة التطوير عندك حاليًا
حسب مسار D:\\taxi-project\\...). الخوارزمية قياسية وموثّقة علنًا.
"""

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(lng, lat, precision=7):
    """
    يحوّل إحداثيات (lng, lat) إلى نص geohash بطول precision حرفًا.
    نفس الإحداثي دائمًا يعطي نفس النص (deterministic) - وهذا بالضبط ما
    نحتاجه لتجميع السائقين/العملاء القريبين في نفس "الخلية" المكانية.
    """
    lat_range = [-90.0, 90.0]
    lng_range = [-180.0, 180.0]

    geohash_chars = []
    bit = 0
    ch = 0
    even = True  # نبدأ بتقسيم خط الطول (lng) دائمًا، حسب معيار geohash القياسي

    while len(geohash_chars) < precision:
        if even:
            mid = (lng_range[0] + lng_range[1]) / 2
            if lng > mid:
                ch = (ch << 1) | 1
                lng_range[0] = mid
            else:
                ch = ch << 1
                lng_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat > mid:
                ch = (ch << 1) | 1
                lat_range[0] = mid
            else:
                ch = ch << 1
                lat_range[1] = mid

        even = not even
        bit += 1

        if bit == 5:
            geohash_chars.append(_BASE32[ch])
            bit = 0
            ch = 0

    return "".join(geohash_chars)