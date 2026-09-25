"""
SharedCompatibilityService — هل تصلح هذه السيارة المشتركة لهذا الراكب؟

دوال خالصة بلا Redis وبلا قاعدة: مدخلاتها أرقام ومخرجاتها درجة وسبب.
هذا مقصود - القاعدة التي تقرر ما يظهر للزبون يجب أن تكون قابلة للاختبار
بمعزل عن أي بنية تحتية، وأن تُعاير بالأرقام لا بالحدس.

الخصوصية مبنيّة في المدخلات لا مضافة عليها: الدالة لا تستقبل وجهة الركّاب
الحاليين أصلًا، بل خليّة geohash خشنة (4 إلى 6 محارف، أي 20كم إلى 1.2كم)
يقرّر الأدمن دقّتها لكل مدينة. أدقّ ما يمكن للفلترة أن تعرفه عن وجهة راكب
آخر هو "في أي ربع من المدينة" لا "في أي شارع".
"""
from math import radians, degrees, sin, cos, sqrt, atan2


# -----------------------------------------------------------------
# أوزان الدرجة. مجموعها 100.
# -----------------------------------------------------------------

WEIGHT_DESTINATION = 50   # الأثقل: وجهتان متقاربتان تعنيان مسارًا مشتركًا حقيقيًا
WEIGHT_DIRECTION = 30     # ثم الاتجاه: لا فائدة من وجهة قريبة خلف ظهر السائق
WEIGHT_DETOUR = 20        # ثم كلفة الانعراج على الركّاب الحاليين

# انعراج يتجاوز هذه النسبة من المسافة المتبقية يُرفض مهما كانت الدرجة.
# نصف المسافة المتبقية حدّ سخيّ عمدًا في سوق أول، ويُشدَّد بعد المعايرة.
MAX_DETOUR_RATIO = 0.5

# فرق اتجاه يتجاوز هذا يعني عمليًا وجهة معاكسة.
MAX_BEARING_DIFF_DEGREES = 90.0

EARTH_RADIUS_KM = 6371.0

_GEOHASH_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


# =================================================================
# جغرافيا
# =================================================================

def haversine_km(lng1, lat1, lng2, lat2):
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lng1, lat2, lng2])
    dlat, dlon = lat2_r - lat1_r, lon2_r - lon1_r
    h = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * atan2(sqrt(h), sqrt(1 - h))


def bearing_degrees(lng1, lat1, lng2, lat2):
    """الاتجاه من النقطة الأولى إلى الثانية، 0=شمال، بالساعة."""
    lat1_r, lat2_r = radians(lat1), radians(lat2)
    dlon = radians(lng2 - lng1)

    x = sin(dlon) * cos(lat2_r)
    y = cos(lat1_r) * sin(lat2_r) - sin(lat1_r) * cos(lat2_r) * cos(dlon)

    return (degrees(atan2(x, y)) + 360.0) % 360.0


def bearing_difference(bearing_a, bearing_b):
    """أصغر فرق زاوي بين اتجاهين، من 0 إلى 180."""
    diff = abs((bearing_a - bearing_b) % 360.0)
    return min(diff, 360.0 - diff)


def geohash_decode(cell):
    """
    مركز خليّة geohash وأبعادها: (lng, lat, نصف الامتداد بالدرجات طولًا وعرضًا).

    نكتبها هنا بدل استيراد فك التشفير من مكان آخر لأن هذه الوحدة يجب أن
    تبقى بلا اعتماديات - وهي 20 سطرًا من خوارزمية ثابتة لا تتغيّر.
    """
    if not cell:
        return None

    lat_range = [-90.0, 90.0]
    lng_range = [-180.0, 180.0]
    is_longitude = True

    for char in str(cell).lower():
        index = _GEOHASH_BASE32.find(char)

        if index < 0:
            return None

        for mask in (16, 8, 4, 2, 1):
            target = lng_range if is_longitude else lat_range
            middle = (target[0] + target[1]) / 2.0

            if index & mask:
                target[0] = middle
            else:
                target[1] = middle

            is_longitude = not is_longitude

    return (
        (lng_range[0] + lng_range[1]) / 2.0,
        (lat_range[0] + lat_range[1]) / 2.0,
        (lng_range[1] - lng_range[0]) / 2.0,
        (lat_range[1] - lat_range[0]) / 2.0,
    )


def cell_radius_km(cell):
    """نصف قطر تقريبي للخليّة بالكيلومترات — هامش الخطأ المقبول في المقارنة."""
    decoded = geohash_decode(cell)

    if decoded is None:
        return None

    lng, lat, half_lng, half_lat = decoded

    return haversine_km(lng - half_lng, lat - half_lat, lng + half_lng, lat + half_lat) / 2.0


# =================================================================
# الدرجة
# =================================================================

class SharedCompatibilityService:

    @classmethod
    def evaluate(
        cls,
        driver_lng,
        driver_lat,
        driver_dest_cell,
        rider_pickup_lng,
        rider_pickup_lat,
        rider_dest_lng,
        rider_dest_lat,
        free_seats=0,
        passenger_count=1,
        min_score=55,
        max_detour_ratio=MAX_DETOUR_RATIO,
    ):
        """
        يرجّع dict: {"eligible": bool, "score": int, "reason": str,
                     "detour_km": float, "bearing_diff": float}

        السبب مُرجَّع دائمًا حتى في حالة القبول: لوحة الإدارة تحتاجه لمعايرة
        shared_min_compatibility_score على بيانات حقيقية بدل تخمين رقم.
        """
        if free_seats < passenger_count:
            return cls._reject(0, "لا مقاعد كافية")

        decoded = geohash_decode(driver_dest_cell)

        if decoded is None:
            return cls._reject(0, "وجهة السيارة غير معروفة")

        dest_lng, dest_lat = decoded[0], decoded[1]
        tolerance_km = max(cell_radius_km(driver_dest_cell) or 1.0, 0.5)

        # --- 1) الاتجاه: فلتر قاسٍ قبل أي حساب آخر -------------------
        route_bearing = bearing_degrees(driver_lng, driver_lat, dest_lng, dest_lat)
        rider_bearing = bearing_degrees(
            driver_lng, driver_lat, rider_dest_lng, rider_dest_lat
        )
        bearing_diff = bearing_difference(route_bearing, rider_bearing)

        if bearing_diff > MAX_BEARING_DIFF_DEGREES:
            return cls._reject(
                0, "الوجهة في الاتجاه المعاكس", bearing_diff=bearing_diff
            )

        # --- 2) الانعراج: كم يُطيل هذا الراكب طريق الحاليين؟ ----------
        remaining_km = haversine_km(driver_lng, driver_lat, dest_lng, dest_lat)

        with_rider_km = (
            haversine_km(driver_lng, driver_lat, rider_pickup_lng, rider_pickup_lat)
            + haversine_km(
                rider_pickup_lng, rider_pickup_lat, rider_dest_lng, rider_dest_lat
            )
            + haversine_km(rider_dest_lng, rider_dest_lat, dest_lng, dest_lat)
        )

        detour_km = max(with_rider_km - remaining_km, 0.0)
        detour_ratio = detour_km / remaining_km if remaining_km > 0.3 else 1.0

        if detour_ratio > max_detour_ratio:
            return cls._reject(
                0,
                f"انعراج {int(detour_km * 1000)}م يتجاوز الحد",
                detour_km=detour_km,
                bearing_diff=bearing_diff,
            )

        # --- 3) الدرجة ------------------------------------------------
        destination_gap_km = haversine_km(
            rider_dest_lng, rider_dest_lat, dest_lng, dest_lat
        )

        # داخل الخليّة نفسها = درجة كاملة. المقارنة بنصف قطر الخليّة لا برقم
        # ثابت: الأدمن حين يغيّر الدقّة يغيّر معها معنى "قريب" تلقائيًا.
        destination_score = WEIGHT_DESTINATION * cls._decay(
            destination_gap_km, tolerance_km * 2.0
        )
        direction_score = WEIGHT_DIRECTION * (
            1.0 - (bearing_diff / MAX_BEARING_DIFF_DEGREES)
        )
        detour_score = WEIGHT_DETOUR * (1.0 - (detour_ratio / max_detour_ratio))

        score = int(round(destination_score + direction_score + detour_score))
        score = max(0, min(score, 100))

        eligible = score >= int(min_score or 0)

        return {
            "eligible": eligible,
            "score": score,
            "reason": "متوافق" if eligible else "درجة التوافق دون الحد",
            "detour_km": round(detour_km, 2),
            "bearing_diff": round(bearing_diff, 1),
            "route_bearing": round(route_bearing, 1),
        }

    # -------------------------------------------------------------

    @staticmethod
    def _decay(value, scale):
        """1 عند الصفر، وتتلاشى تدريجيًا - لا عتبة حادّة تقفز عندها النتيجة."""
        if scale <= 0:
            return 0.0
        return max(0.0, 1.0 - (value / scale))

    @staticmethod
    def _reject(score, reason, detour_km=0.0, bearing_diff=None):
        return {
            "eligible": False,
            "score": score,
            "reason": reason,
            "detour_km": round(detour_km, 2),
            "bearing_diff": round(bearing_diff, 1) if bearing_diff is not None else None,
            "route_bearing": None,
        }
