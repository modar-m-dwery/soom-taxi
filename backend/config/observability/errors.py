"""
رموز الأخطاء — الطبقة التي ينقصها المشروع كلّه اليوم.

المشكلة الحقيقية موجودة في كودك حرفيًا:

    # matching/services/matching.py:528
    except MatchingError as exc:
        if str(exc) == "Offer has expired.":

منطق أعمال يتفرّع على مطابقة نصّ. أضِف نقطة للرسالة أو ترجمها، فيصير
الشرط False بصمت. وتطبيق الجوال في الوضع نفسه: لا يملك إلا مقارنة نصوص
عربية وإنجليزية مختلطة.

الحلّ هنا لا يطلب تعديل خدماتك الآن: جدول ترجمة من نوع الاستثناء ونصّه
إلى رمز ثابت. تُصلح الخدمات تدريجيًا لاحقًا (بأن ترفع AppError برمزها)،
وحتى ذلك الحين تحصل على رمز مشتقّ من نوع الاستثناء على الأقل.
"""


class AppError(Exception):
    """
    الاستثناء الذي ينبغي أن ترثه أخطاء الأعمال الجديدة.

        raise AppError("لا مقاعد كافية.", code="shared.no_seats")

    الرسالة للمستخدم، والرمز للتطبيق. الفصل بينهما يعني أنك تستطيع تحسين
    الصياغة العربية متى شئت بلا أن تكسر عميلًا واحدًا.
    """

    default_code = "error"
    status_code = 400

    def __init__(self, message="", code="", status_code=None, fields=None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        if status_code is not None:
            self.status_code = status_code
        self.fields = fields or {}


# ---------------------------------------------------------------------
# جدول الترجمة للاستثناءات القائمة
# ---------------------------------------------------------------------
#
# المفتاح اسم الصنف كنصّ لا الصنف نفسه: استيراد كل تطبيقات المشروع داخل
# config يخلق دورة استيراد عند أول توسّع، والاسم يكفي.

EXCEPTION_CODES = {
    "MatchingError":          ("matching.failed", 400),
    "SharedMatchingError":    ("shared.failed", 400),
    "InvitationError":        ("invitation.failed", 400),
    "TripError":              ("trip.failed", 400),
    "RideRequestValidationError": ("ride.invalid", 400),
    "RatingError":            ("rating.failed", 400),
    "ComplaintError":         ("complaint.failed", 400),
    "PresenceError":          ("presence.failed", 400),
    "VehicleError":           ("vehicle.failed", 400),
    "OpsError":               ("ops.failed", 400),
    "RoutingError":           ("routing.unavailable", 503),
    "PricingError":           ("pricing.failed", 400),
}


# رموز أدقّ مشتقّة من نصّ الرسالة — مرحلة انتقالية.
#
# هذه ليست الحلّ النهائي بل جسر: تعطي التطبيق رمزًا يعتمد عليه اليوم،
# وتُحذف سطرًا سطرًا كلّما رفعت خدمة AppError برمزها الصريح.

MESSAGE_CODES = {
    "Offer has expired.":                    "offer.expired",
    "Ride is no longer searching.":          "ride.not_searching",
    "Driver is not eligible":                "driver.not_eligible",
    "Shared ride group is no longer active.": "shared.group_inactive",
    "هذه الدعوة لم تعد صالحة.":               "invitation.expired",
    "هذه السيارة لم تعد متاحة لطلبك. اختر سيارة أخرى.": "driver.unavailable",
    "لديك دعوة معلّقة بالفعل. انتظر ردّ السائق أو ألغِ الدعوة.": "invitation.parallel_limit",
    "هذا السائق رفض طلبك قبل قليل. اختر سيارة أخرى.": "invitation.cooldown",
    "لا يمكن بدء الرحلة قبل تسجيل الوصول إلى نقطة الالتقاء.": "trip.not_arrived",
    "لا يمكن إنهاء رحلة لم تبدأ بعد.":         "trip.not_started",
    "هذه الرحلة ليست لك.":                    "trip.forbidden",
    "لا يوجد سائق مثبَّت على هذا الطلب.":       "trip.no_driver",
    "قيّمتَ هذه الرحلة من قبل.":                "rating.duplicate",
    "التقييم من 1 إلى 5.":                     "rating.out_of_range",
}


def resolve(exc):
    """
    يرجّع (code, status_code) لأي استثناء.

    الترتيب: AppError الصريح، ثم نصّ معروف، ثم نوع معروف، ثم عام.
    """
    if isinstance(exc, AppError):
        return exc.code, exc.status_code

    message = str(exc)

    if message in MESSAGE_CODES:
        name = type(exc).__name__
        _, status = EXCEPTION_CODES.get(name, ("", 400))
        return MESSAGE_CODES[message], status

    name = type(exc).__name__

    if name in EXCEPTION_CODES:
        return EXCEPTION_CODES[name]

    return "error", 400
