from django.contrib.gis.db import models as gis_models
from django.core.exceptions import ValidationError
from django.db import models


# =====================================================================
# نماذج التسعير - مستخلصة من مسح تنظيمي لـ11 دولة عربية و14 سوقًا عالمية.
#
# القاعدة التي حكمت التصميم: لا توجد دولة تمنع "مزايدة السائقين" بالاسم.
# الخطر يأتي من *التعارض مع تعرفة إلزامية قائمة* (سابقة الفلبين 2024).
# لذلك الخطط ليست مستويات تصاعدية، بل آليات مستقلة يُفعَّل منها ما يوافق
# قانون البلد - وقد تُفعَّل أكثر من واحدة معًا.
# =====================================================================


class PricingPolicy(models.TextChoices):
    PLATFORM_FIXED = "platform_fixed", "سعر المنصة الثابت (أوبر/كريم)"
    REGULATED_TARIFF = "regulated_tariff", "تعرفة رسمية إلزامية (الأردن/دبي)"
    TARIFF_CORRIDOR = "tariff_corridor", "ممر تعرفة: أرضية وسقف (الهند/إندونيسيا)"
    DRIVER_BIDDING = "driver_bidding", "مزايدة السائقين (السائق يقترح سعره)"
    CUSTOMER_BIDDING = "customer_bidding", "الزبون يقترح السعر (نموذج inDrive)"


class SurgeMode(models.TextChoices):
    DISABLED = "disabled", "معطّل"
    CAPPED = "capped", "خوارزمي بسقف أقصى"
    REGULATOR_TIERS = "regulator_tiers", "نوافذ ورسوم تحددها الهيئة (دبي)"
    FREE = "free", "خوارزمي بلا سقف"


class PriceChangeWorkflow(models.TextChoices):
    NONE = "none", "بلا إجراء"
    NOTIFY = "notify", "إخطار مسبق للجهة المنظِّمة (مصر)"
    APPROVAL = "approval", "موافقة مسبقة قبل التفعيل (السعودية)"


class SharedDestinationPrecision(models.IntegerChoices):
    """
    دقّة تقريب وجهة الركّاب الحاليين المعروضة لمرشّح الانضمام في الرحلات
    المشتركة. الأدمن يختار حسب كثافة مدينته - لكن ليس أدقّ من 6.

    عمدًا لا نسمح بـ7 (~150م) ولا 8 (~38م): هذه دقّة تكشف حيًّا بعينه أو
    مبنى، وتحوّل الخريطة من خدمة إلى أداة تتبّع. حاجز على مستوى الموديل،
    لا على مستوى الاتفاق.
    """
    COARSE = 4, "~20 كم — حماية قصوى (كثافة منخفضة/ريف)"
    BALANCED = 5, "~5 كم — متوازن (الافتراضي)"
    FINE = 6, "~1.2 كم — فلترة دقيقة (مدن مزدحمة)"


class ServiceArea(models.Model):
    """
    منطقة خدمة مستقلة (مدينة/محافظة) تُدار بالكامل من لوحة الإدارة.

    القرار المعماري: لا شيء خاص بمدينة أو بدولة مكوَّد يدويًا في أي مكان.
    إضافة سوق جديد = صف جديد هنا بإعداداته، بلا تعديل كود ولا نشر.
    """

    # -----------------------------------------------------------------
    # الهوية
    # -----------------------------------------------------------------

    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="رمز قصير فريد يظهر داخل area_id، مثال: JAB, LAT, DAM",
    )

    name = models.CharField(max_length=100)

    country_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="ISO 3166-1 alpha-2، مثال: SY, JO, AE. للتقارير والامتثال.",
    )

    currency_code = models.CharField(
        max_length=3,
        default="SYP",
        help_text="ISO 4217. كل المبالغ في هذه المنطقة بهذه العملة.",
    )

    # -----------------------------------------------------------------
    # الحدود الجغرافية
    # -----------------------------------------------------------------

    boundary = gis_models.PolygonField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
        help_text=(
            "حدود المدينة الدقيقة (Polygon). اتركها فارغة واستخدم "
            "center + fallback_radius_km كبديل دائري مؤقت لحين توفرها."
        ),
    )

    center = gis_models.PointField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
    )

    fallback_radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=15,
        help_text="يُستخدم فقط إذا لم تُحدَّد boundary دقيقة لهذه المدينة.",
    )

    # -----------------------------------------------------------------
    # الخريطة الحيّة
    # -----------------------------------------------------------------

    marketplace_cell_precision = models.PositiveSmallIntegerField(
        default=5,
        help_text=(
            "دقة خلايا geohash لهذه المدينة (عمليًا 5–8). "
            "5≈4.9كم · 6≈1.2كم · 7≈150م · 8≈38م. "
            "الزبون لا يرى إلّا سائقي خليّته: بدقّة 7 كان سائقٌ على بُعد كيلومتر "
            "لا يظهر على الخريطة (وُجد بجهازين حقيقيّين في 2026-09-21)، "
            "فالافتراض 5 ليوافق نصف قطر المطابقة (5 كم)."
        ),
    )

    shared_destination_precision = models.PositiveSmallIntegerField(
        choices=SharedDestinationPrecision.choices,
        default=SharedDestinationPrecision.BALANCED,
        help_text=(
            "كم نُقرِّب وجهة الركّاب الحاليين عند عرض سيارة مشتركة "
            "لمرشّح انضمام. كلما زادت الدقّة تحسّنت الفلترة وقلّت الخصوصية."
        ),
    )

    shared_min_compatibility_score = models.PositiveSmallIntegerField(
        default=55,
        help_text=(
            "أقل درجة توافق (من 100) تُظهر سيارة مشتركة كخيار صالح. "
            "أقل = مطابقات أكثر وانعراج أكبر."
        ),
    )

    # -----------------------------------------------------------------
    # أنصاف أقطار المطابقة
    # -----------------------------------------------------------------
    #
    # لماذا لكلّ مدينة لا للمنصّة: نصف القطر ليس رقمًا تقنيًّا بل وصفٌ
    # لجغرافيا. جبلة مدينة ساحلية صغيرة يقطعها السائق في دقائق، فخمسة
    # كيلومترات فيها تعني «كلّ المدينة». والريف المحيط بها تبعد نقاطه
    # عشرين كيلومترًا، فخمسةٌ هناك تعني «لا سائق أبدًا». والمشغّل هو من
    # يعرف مدينته لا من كتب الشيفرة.
    #
    # وضبطه خطيرٌ في الاتجاهين، ولذلك حدوده مُتحقَّق منها:
    #   • صغيرًا جدًّا → الطلب ينتهي بلا سائق ويظنّ الزبون أنّ المنصّة فارغة
    #   • كبيرًا جدًّا → يُطابَق سائق يحتاج ثلث ساعة ليصل، فيلغي الزبون
    #
    # `default_matching_radius_km` هو نصف قطر **الطلب الفوري**، وهو الأهمّ.
    # كان اسمه يوحي بأنّه افتراضٌ عامّ، وكان يُقرأ في مسار واحد فقط بينما
    # يقرأ محرّك المطابقة رقمًا عالميًّا من الإعدادات — أي أنّ تغييره من
    # الأدمن كان يبدّل ما يراه الزبون على الخريطة ولا يبدّل من يُطابَق
    # فعلًا. الآن هو المصدر الوحيد للمسارين.

    default_matching_radius_km = models.DecimalField(
        max_digits=6, decimal_places=2, default=5,
        help_text=(
            "نصف قطر البحث للطلبات الفورية (كم). هذا هو الرقم الذي يحدّد "
            "مَن يُطابَق فعلًا ومَن يظهر على خريطة الزبون."
        ),
    )

    marketplace_radius_km = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text=(
            "نصف قطر الطلبات المجدولة والرحلات المنشورة (كم). أوسع من "
            "الفوري عمدًا: مَن يحجز لغدٍ يقبل سائقًا أبعد. "
            "فارغ = الافتراضي العامّ."
        ),
    )

    shared_join_radius_km = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text=(
            "أقصى مسافة بين نقطتَي التقاط في المشاركة الفورية (كم). "
            "رفعه يزيد المطابقات ويزيد انعراج الراكب الأوّل. فارغ = 3 كم."
        ),
    )

    shared_scheduled_pickup_radius_km = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="نطاق التقاط المشاركة المجدولة (كم). فارغ = 10 كم.",
    )

    shared_scheduled_dest_radius_km = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="نطاق توافق الوجهة في المشاركة المجدولة (كم). فارغ = 15 كم.",
    )

    shared_scheduled_time_window_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "فرق الوقت المقبول بين رحلتين مجدولتين لتُعدّا متوافقتين "
            "(دقيقة). فارغ = 60 دقيقة."
        ),
    )

    # -----------------------------------------------------------------
    # المهل التشغيلية
    # -----------------------------------------------------------------
    #
    # هذه الأرقام كانت موزّعة بين متغيّرات بيئة وثوابت مكتوبة في الشيفرة —
    # وأسوأها نافذة البحث: كانت `timedelta(minutes=10)` داخل الدالّة نفسها،
    # أي أنّ تغييرها كان يحتاج تعديل شيفرة ونشرًا.
    #
    # وهي بطبيعتها لكلّ مدينة لا للمنصّة كلّها: مدينة صغيرة كثيفة تُغلق
    # المزاد في عشرين ثانية، ومدينة متباعدة تحتاج ضعفها. جعلها عالميّة يعني
    # أنّ ضبطها لمدينة يفسدها للأخرى.
    #
    # كلّها تقبل NULL بمعنى «استعمل الافتراضي العامّ من الإعدادات»: فلا
    # ترحيلٌ يفرض رقمًا على مدينة قائمة، ولا يضطرّ المشغّل لملء كلّ حقل
    # ليضبط واحدًا. اقرأها عبر ServiceAreaSettings لا مباشرةً.

    offer_ttl_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text=(
            "مهلة صلاحية عرض السائق قبل انتهائه تلقائيًّا. "
            "فارغ = الافتراضي العامّ (RIDE_OFFER_TTL_SECONDS)."
        ),
    )

    ride_search_window_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "كم يبقى الطلب الفوري يبحث عن سائق قبل أن ينتهي. "
            "لا يُطبَّق على الطلبات المجدولة. فارغ = 10 دقائق."
        ),
    )

    presence_stale_seconds = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "انقطاع نبض السائق هذه المدّة يُخرجه من الأسطول المرئي. "
            "خفضه يُنقّي الخريطة ويقسو على الشبكات الضعيفة. فارغ = 60 ثانية."
        ),
    )

    presence_fresh_seconds = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "أقصى عمر للنبض ليُعدّ السائق حاضرًا لا متأخّرًا. "
            "يجب أن يكون أصغر من مهلة الانقطاع. فارغ = 30 ثانية."
        ),
    )

    location_max_age_seconds = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "أقصى عمر لموقع السائق في القاعدة ليدخل المطابقة. "
            "فارغ = الافتراضي العامّ (MATCHING_LOCATION_MAX_AGE_SECONDS)."
        ),
    )

    invitation_reject_cooldown_seconds = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "بعد رفض سائق لزبون، كم يبقى مخفيًّا عنه. "
            "فارغ = الافتراضي العامّ."
        ),
    )

    arrival_radius_m = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "كم مترًا يُقبل بينها وبين نقطة الالتقاء لتسجيل «وصلت». "
            "مدينة بأزقّة ضيّقة تحتاج رقمًا أكبر. فارغ = 200 متر."
        ),
    )

    dropoff_radius_m = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=(
            "كم مترًا يُقبل بينها وبين الوجهة لإنهاء الرحلة بلا تعليم "
            "للمراجعة. فارغ = 300 متر."
        ),
    )

    # -----------------------------------------------------------------
    # الدعوة المباشرة (خريطة السيارات الحيّة)
    # -----------------------------------------------------------------

    invitation_ttl_options = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "المهل (بالثواني) التي تُعرض على الزبون ليختار منها قبل إرسال "
            'الدعوة. مثال: [20, 40, 60]. القيمة خارج القائمة تُرفض من الخادم.'
        ),
    )

    invitation_ttl_default = models.PositiveSmallIntegerField(
        default=20,
        help_text="المهلة المختارة مسبقًا. يجب أن تكون ضمن القائمة أعلاه.",
    )

    invitation_max_parallel = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "كم دعوة يمكن للزبون إرسالها في وقت واحد للطلب نفسه. "
            "1 = سيارة واحدة ثم انتظار (الموصى به وما تنص عليه الوثيقة)."
        ),
    )

    invitation_allowed_modes = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "أنماط الخدمة التي تُفعَّل فيها الخريطة الحيّة والدعوة المباشرة. "
            'مثال: ["fast", "express"] أو أضف "shared" لتفعيل المشتركة.'
        ),
    )

    # -----------------------------------------------------------------
    # نطاق البحث الذي يختاره الزبون، والإرسال لأقرب سائق
    #
    # داخل المدينة كلّ عشرة أمتار سيارة، وفي الضيعة أقربها على بعد
    # كيلومترات. رقمٌ واحد للمنطقة يظلم أحدهما، فالزبون يختار من قائمة
    # يضعها المشغّل — والخادم يرفض ما خارجها ولا يتجاوز نصف قطر المنطقة.
    # -----------------------------------------------------------------

    search_radius_options_km = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "أنصاف الأقطار (كم) التي يختار منها الزبون نطاق البحث. "
            "مثال: [1, 3, 5, 10]. فارغ = لا اختيار، ويُستعمل نصف قطر المنطقة. "
            "القيم الأكبر من نصف قطر الطلب الفوري تُقصّ إليه."
        ),
    )

    auto_dispatch_ttl_seconds = models.PositiveSmallIntegerField(
        default=15,
        help_text=(
            "«الأقرب»: كم ثانية ينتظر النظام ردّ السائق قبل أن ينتقل "
            "تلقائيًّا إلى السائق التالي."
        ),
    )

    auto_dispatch_max_attempts = models.PositiveSmallIntegerField(
        default=5,
        help_text=(
            "«الأقرب»: كم سائقًا يُجرَّب بالتتابع قبل أن يُترك الطلب لعروض "
            "السائقين العاديّة."
        ),
    )

    # -----------------------------------------------------------------
    # سياسة الإلغاء — بلا غرامات نقديّة، بعدّاد مخالفات
    #
    # في سوقٍ فقير، غرامةٌ على زبون ألغى تُبعده عن التطبيق كلّه. والإلغاء
    # المجّاني بلا حدّ يستنزف السائق الذي قاد إليه. الوسط: إلغاءٌ مجّانيّ
    # حيث يكون عادلًا، ومخالفةٌ تُحسب حيث لا يكون، وعقوبةٌ مؤقّتة لا ماليّة.
    # -----------------------------------------------------------------

    cancel_free_window_seconds = models.PositiveIntegerField(
        default=120,
        help_text="إلغاء الزبون مجّانيّ خلال هذه الثواني بعد تثبيت السائق.",
    )

    cancel_driver_late_grace_minutes = models.PositiveSmallIntegerField(
        default=5,
        help_text=(
            "إن تأخّر السائق عن وقت وصوله المعلن بأكثر من هذه الدقائق، "
            "فإلغاء الزبون مجّانيّ مهما مضى من وقت."
        ),
    )

    cancel_wait_minutes = models.PositiveSmallIntegerField(
        default=5,
        help_text=(
            "إلغاءٌ بعد أن وصل السائق وانتظر هذه الدقائق يُحسب مخالفتين: "
            "السائق خسر المشوار والوقت معًا."
        ),
    )

    late_cancel_strike_limit = models.PositiveSmallIntegerField(
        default=3,
        help_text="عدد مخالفات الإلغاء المتأخّر التي تُطلق العقوبة. 0 = بلا عقوبة.",
    )

    late_cancel_window_days = models.PositiveSmallIntegerField(
        default=7,
        help_text="المخالفات تُعدّ ضمن هذه الأيّام الأخيرة فقط.",
    )

    late_cancel_penalty_hours = models.PositiveSmallIntegerField(
        default=24,
        help_text=(
            "مدّة العقوبة: الزبون يطلب بالعروض وحدها («الأقرب» و«اختر "
            "سيارتك» تتوقّفان)، ويرى السائقون شارةً على طلبه."
        ),
    )

    driver_cancel_daily_limit = models.PositiveSmallIntegerField(
        default=3,
        help_text="كم مرّة يلغي السائق بعد القبول في اليوم قبل إيقافه مؤقّتًا. 0 = بلا حدّ.",
    )

    driver_cancel_block_minutes = models.PositiveSmallIntegerField(
        default=60,
        help_text="مدّة إيقاف السائق عن العروض والدعوات بعد تجاوز الحدّ.",
    )

    # -----------------------------------------------------------------
    # التسعير - القلب الجديد
    # -----------------------------------------------------------------

    allowed_pricing_policies = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "خطط التسعير المسموح بها في هذه المنطقة. يمكن اختيار أكثر من "
            "واحدة. اختر ما يوافق قانون البلد فعلًا."
        ),
    )

    default_pricing_policy = models.CharField(
        max_length=30,
        choices=PricingPolicy.choices,
        default=PricingPolicy.PLATFORM_FIXED,
        help_text="الخطة المطبَّقة تلقائيًا. يجب أن تكون ضمن المسموح بها.",
    )

    surge_mode = models.CharField(
        max_length=20,
        choices=SurgeMode.choices,
        default=SurgeMode.DISABLED,
        help_text=(
            "تنبيه: 'مسموح بالتسعير الديناميكي' و'المنصة تحسبه' شيئان "
            "مختلفان. دبي تسمح بالتغيّر لكن الهيئة هي من تحدد النوافذ والرسوم "
            "→ اختر regulator_tiers لا capped."
        ),
    )

    surge_max_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="مطلوب مع surge_mode=capped. مثال: 2.00 (الهند)، 1.75 (مدريد).",
    )

    fare_floor_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "أرضية السعر كنسبة من تسعيرة المنصة. مطلوبة مع ممر التعرفة. "
            "مثال: 0.50 (الهند)، 0.93 (ألمانيا: حد أدنى لحماية التاكسي)."
        ),
    )

    fare_cap_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="سقف السعر كنسبة من تسعيرة المنصة. مثال: 2.00 (الهند).",
    )

    min_fare_absolute = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="حد أدنى مطلق للأجرة بعملة المنطقة. مثال: 13 درهم في دبي.",
    )

    driver_min_share_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="أقل نسبة يجب أن يقبضها السائق من الأجرة. مثال: 80 (الهند).",
    )

    commission_cap_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="سقف عمولة المنصة. مثال: 15 (إندونيسيا)، 18 (كينيا). MVP=0.",
    )

    # -----------------------------------------------------------------
    # الترويج — خطّة التسعين يومًا: «أوّل مشوار بنصف السعر، بسقفٍ محدَّد لا
    # نسبة» و«زبون يجلب زبونًا: مشوار مخفَّض للاثنين بعد أن يُتمّ الجديد
    # رحلته الأولى». إعداداتٌ لكلّ مدينة تُطفأ بالصفر — لا شيفرة.
    # -----------------------------------------------------------------
    first_ride_discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="نسبة خصم أوّل مشوار للزبون الجديد. 0 = معطَّل. مثال: 50.",
    )
    first_ride_discount_cap = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="سقف الخصم بالعملة المحلّية (الخطّة: سقفٌ لا نسبة). فارغ = بلا سقف.",
    )
    referral_reward = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="رصيدٌ يُمنح للداعي والمدعوّ معًا بعد أوّل رحلة مكتملة للمدعوّ. 0 = معطَّل.",
    )

    allow_renegotiation_after_match = models.BooleanField(
        default=False,
        help_text=(
            "هل يجوز تعديل السعر بعد تثبيت السائق؟ ماليزيا تحظره صراحةً. "
            "اتركه معطّلًا ما لم يكن مسموحًا صراحةً."
        ),
    )

    price_change_workflow = models.CharField(
        max_length=20,
        choices=PriceChangeWorkflow.choices,
        default=PriceChangeWorkflow.NONE,
        help_text=(
            "الفرق تشغيلي جوهري: 'إخطار' يسجّل التغيير ويمضي، "
            "'موافقة' يحجب التفعيل حتى ردّ الجهة."
        ),
    )

    # -----------------------------------------------------------------
    # سجل الامتثال - ليس منطقًا، لكنه يوفّر ساعات عند أي مراجعة قانونية
    # -----------------------------------------------------------------

    regulator_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="مثال: هيئة تنظيم النقل البري (LTRC) — الأردن",
    )

    legal_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="رقم القانون/اللائحة التي بُنيت عليها الإعدادات أعلاه.",
    )

    compliance_note = models.TextField(
        blank=True,
        help_text=(
            "ملاحظات المراجعة القانونية. إن كان الوضع التنظيمي غامضًا "
            "(قطر/الكويت/سوريا) سجّل ذلك هنا صراحةً - الصمت ليس إذنًا."
        ),
    )

    # -----------------------------------------------------------------
    # معايرة التقدير الداخلي للمسافة والزمن
    #
    # تُستخدم حين يتعذّر مزوّد التوجيه (راجع maps/services/routing.py).
    # قيمتان لكلّ منطقة لا قيمة عالمية: التفاف شوارع جبلة الساحلية ليس
    # التفاف شبكة دمشق، وسرعة الذروة في مدينة صغيرة ليست سرعة العاصمة.
    # عايرهما بمقارنة عيّنة من الرحلات الحقيقية بالمسافة الهوائية.
    # -----------------------------------------------------------------

    road_detour_factor = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "نسبة مسافة الطريق إلى المسافة الهوائية. 1.35 نقطة بداية "
            "معقولة لمدينة ساحلية. اتركه فارغًا لاستخدام الافتراضي العام."
        ),
    )

    average_speed_kmh = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "السرعة الوسطية الفعلية بما فيها التوقّف والإشارات — لا الحدّ "
            "الأقصى المسموح. 30 كم/سا نقطة بداية معقولة."
        ),
    )

    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"ServiceArea({self.code} - {self.name})"

    # -----------------------------------------------------------------
    # DEFAULTS
    # -----------------------------------------------------------------

    @staticmethod
    def default_invitation_ttl_options():
        return [20, 40, 60]

    @staticmethod
    def default_invitation_allowed_modes():
        return ["fast", "express"]

    @staticmethod
    def default_pricing_policies():
        return [PricingPolicy.PLATFORM_FIXED, PricingPolicy.DRIVER_BIDDING]

    def save(self, *args, **kwargs):
        # JSONField(default=list) يعطي قائمة فارغة، وهي ليست إعدادًا صالحًا.
        # نملأ الافتراضات المعقولة عند أول حفظ بدل ترك المنطقة معطّلة صامتًا.
        if not self.invitation_ttl_options:
            self.invitation_ttl_options = self.default_invitation_ttl_options()
        if not self.invitation_allowed_modes:
            self.invitation_allowed_modes = self.default_invitation_allowed_modes()
        if not self.allowed_pricing_policies:
            self.allowed_pricing_policies = self.default_pricing_policies()
        return super().save(*args, **kwargs)

    # -----------------------------------------------------------------
    # VALIDATION - تمنع تركيبات غير متسقة قبل أن تصل للإنتاج
    # -----------------------------------------------------------------

    def clean(self):
        errors = {}

        valid_policies = {c[0] for c in PricingPolicy.choices}
        policies = set(self.allowed_pricing_policies or [])

        unknown = policies - valid_policies
        if unknown:
            errors["allowed_pricing_policies"] = f"خطط غير معروفة: {sorted(unknown)}"

        if policies and self.default_pricing_policy not in policies:
            errors["default_pricing_policy"] = (
                "الخطة الافتراضية يجب أن تكون ضمن الخطط المسموح بها."
            )

        # تعرفة رسمية إلزامية + مزايدة = تناقض منطقي قبل أن يكون قانونيًا:
        # لا يوجد ما يُزايَد عليه إن كان السعر محددًا من الدولة.
        if PricingPolicy.REGULATED_TARIFF in policies and (
            PricingPolicy.DRIVER_BIDDING in policies
            or PricingPolicy.CUSTOMER_BIDDING in policies
        ):
            errors["allowed_pricing_policies"] = (
                "لا يمكن الجمع بين تعرفة رسمية إلزامية وأي شكل من المزايدة. "
                "إن أردت هامش تفاوض ضمن حدود رسمية استخدم 'ممر تعرفة' بدلًا منها."
            )

        if PricingPolicy.TARIFF_CORRIDOR in policies:
            if self.fare_floor_multiplier is None or self.fare_cap_multiplier is None:
                errors["fare_floor_multiplier"] = (
                    "ممر التعرفة يتطلب تحديد الأرضية والسقف معًا."
                )
            elif not (
                self.fare_floor_multiplier
                <= 1
                <= self.fare_cap_multiplier
            ):
                errors["fare_cap_multiplier"] = (
                    "يجب أن يتحقق: الأرضية ≤ 1.00 ≤ السقف "
                    "(تسعيرة المنصة هي المرجع الذي يدور حوله الممر)."
                )

        if self.surge_mode == SurgeMode.CAPPED and self.surge_max_multiplier is None:
            errors["surge_max_multiplier"] = (
                "الوضع 'خوارزمي بسقف' يتطلب تحديد السقف الأقصى."
            )

        if self.surge_mode == SurgeMode.DISABLED and self.surge_max_multiplier:
            errors["surge_max_multiplier"] = (
                "التسعير الديناميكي معطّل — اترك السقف فارغًا لتفادي الالتباس."
            )

        # الدعوات
        options = self.invitation_ttl_options or []
        if options:
            if not all(isinstance(v, int) and 5 <= v <= 300 for v in options):
                errors["invitation_ttl_options"] = (
                    "كل مهلة يجب أن تكون عددًا صحيحًا بين 5 و300 ثانية."
                )
            elif self.invitation_ttl_default not in options:
                errors["invitation_ttl_default"] = (
                    f"المهلة الافتراضية يجب أن تكون ضمن الخيارات {options}."
                )

        if self.invitation_max_parallel < 1:
            errors["invitation_max_parallel"] = "يجب أن تكون 1 على الأقل."

        if self.boundary is None and self.center is None:
            errors["center"] = (
                "حدّد إمّا boundary دقيقة أو center مع نصف قطر — "
                "وإلا لن تُحلّ أي نقطة إلى هذه المنطقة."
            )

        # ---------------------------------------------------------------
        # المهل التشغيلية
        #
        # الحدود هنا ليست تجميلًا. مهلة عرض من ثانيتين تُنهي كلّ عرض قبل أن
        # يراه الزبون، ونافذة بحث من يوم كامل تملأ لوحة المشغّل بطلبات ميتة.
        # الأدمن أداة تشغيل لا حقل نصّ حرّ، وما يُدخَل هنا يسري فورًا على
        # الإنتاج بلا مراجعة ولا نشر — فالحارس هنا لا في مكان آخر.
        # ---------------------------------------------------------------

        # ---------------------------------------------------------------
        # أنصاف الأقطار
        #
        # الحدّ الأدنى نصف كيلومتر: أصغر منه يجعل الطلب ينتهي بلا سائق في
        # أيّ مدينة حقيقية. والأقصى مئة: أكبر منه يُطابِق سائقًا من مدينة
        # أخرى ويجعل الزبون ينتظر نصف ساعة ثمّ يلغي.
        # ---------------------------------------------------------------

        _radii = [
            ("default_matching_radius_km", 0.5, 100, "نصف قطر الطلب الفوري"),
            ("marketplace_radius_km", 0.5, 200, "نصف قطر المجدول"),
            ("shared_join_radius_km", 0.2, 50, "نصف قطر المشاركة"),
            ("shared_scheduled_pickup_radius_km", 0.5, 100, "التقاط المشاركة المجدولة"),
            ("shared_scheduled_dest_radius_km", 0.5, 200, "وجهة المشاركة المجدولة"),
        ]

        for field, low, high, label in _radii:
            value = getattr(self, field, None)
            if value is not None and not (low <= float(value) <= high):
                errors[field] = f"{label}: القيمة يجب أن تكون بين {low} و{high} كم."

        window = self.shared_scheduled_time_window_minutes
        if window is not None and not (5 <= window <= 720):
            errors["shared_scheduled_time_window_minutes"] = (
                "نافذة الوقت بين 5 دقائق و12 ساعة."
            )

        # المجدول أوسع من الفوري: مَن يحجز لغدٍ يقبل سائقًا أبعد، والعكس
        # تركيبةٌ لا معنى لها — طلبٌ مجدول يرى سائقين أقلّ من الفوري.
        instant = self.default_matching_radius_km
        marketplace = self.marketplace_radius_km
        if (
            instant is not None
            and marketplace is not None
            and float(marketplace) < float(instant)
        ):
            errors["marketplace_radius_km"] = (
                "نصف قطر المجدول لا يصحّ أن يكون أضيق من الفوري."
            )

        _bounds = [
            ("offer_ttl_seconds", 10, 600, "مهلة العرض"),
            ("ride_search_window_minutes", 1, 120, "نافذة البحث"),
            ("presence_stale_seconds", 20, 600, "مهلة الانقطاع"),
            ("presence_fresh_seconds", 5, 300, "مهلة الحضور"),
            ("location_max_age_seconds", 15, 600, "عمر الموقع"),
            ("invitation_reject_cooldown_seconds", 0, 3600, "تهدئة الرفض"),
            ("arrival_radius_m", 20, 2000, "نطاق الوصول"),
            ("dropoff_radius_m", 20, 5000, "نطاق الإنزال"),
        ]

        for field, low, high, label in _bounds:
            value = getattr(self, field, None)
            if value is not None and not (low <= value <= high):
                errors[field] = f"{label}: القيمة يجب أن تكون بين {low} و{high}."

        # الحضور قبل الانقطاع: العكس يجعل السائق «متأخّرًا» ثمّ «حاضرًا» ثمّ
        # يختفي — تسلسلٌ لا معنى له، وأثره سائق يومض على الخريطة.
        fresh = self.presence_fresh_seconds
        stale = self.presence_stale_seconds
        if fresh is not None and stale is not None and fresh >= stale:
            errors["presence_fresh_seconds"] = (
                "مهلة الحضور يجب أن تكون أصغر من مهلة الانقطاع."
            )

        # نطاق الإنزال أضيق من نطاق الالتقاء يعني رحلةً يستحيل إنهاؤها في
        # المكان الذي بدأت منه — تركيبة تُنتج تعليمًا للمراجعة بلا سبب.
        arrival = self.arrival_radius_m
        dropoff = self.dropoff_radius_m
        if arrival is not None and dropoff is not None and dropoff < arrival:
            errors["dropoff_radius_m"] = (
                "نطاق الإنزال لا يصحّ أن يكون أضيق من نطاق الوصول."
            )

        if errors:
            raise ValidationError(errors)

    # -----------------------------------------------------------------
    # القيم الفعلية
    #
    # درس مستفاد: الاعتماد على save() لتعبئة الافتراضات لا يكفي. الهجرة
    # تكتب default=list في الصفوف القائمة مباشرةً بلا استدعاء save()، فتبقى
    # المنطقة بقائمة فارغة إلى أن يحفظها أحد - وقائمة فارغة هنا تعني
    # "الدعوة المباشرة معطّلة في هذه المدينة"، وهو معنى لم يقصده أحد.
    #
    # لذلك القراءة نفسها تحمل الافتراض، لا الكتابة.
    # -----------------------------------------------------------------

    @property
    def effective_pricing_policies(self):
        return self.allowed_pricing_policies or self.default_pricing_policies()

    @property
    def effective_invitation_modes(self):
        return self.invitation_allowed_modes or self.default_invitation_allowed_modes()

    @property
    def effective_ttl_options(self):
        return self.invitation_ttl_options or self.default_invitation_ttl_options()

    @property
    def effective_ttl_default(self):
        options = self.effective_ttl_options
        if self.invitation_ttl_default in options:
            return self.invitation_ttl_default
        return options[0]

    # -----------------------------------------------------------------
    # المهل التشغيلية — قيمة المنطقة، وإلّا الافتراضي العامّ
    #
    # الاستيراد داخل الدالّة مقصود: locations يجب ألّا يستورد settings وقت
    # تحميل النماذج، ولأنّ قراءة الإعداد وقت النداء تجعل override_settings
    # في الاختبارات يعمل كما يتوقّع القارئ.
    # -----------------------------------------------------------------

    def _fallback(self, field, setting_name, hard_default):
        value = getattr(self, field, None)
        if value:
            return value
        from django.conf import settings
        return getattr(settings, setting_name, hard_default)

    @property
    def effective_offer_ttl_seconds(self):
        return self._fallback("offer_ttl_seconds", "RIDE_OFFER_TTL_SECONDS", 90)

    @property
    def effective_ride_search_window_minutes(self):
        return self._fallback(
            "ride_search_window_minutes", "RIDE_SEARCH_WINDOW_MINUTES", 10
        )

    @property
    def effective_presence_stale_seconds(self):
        return self._fallback(
            "presence_stale_seconds", "PRESENCE_HEARTBEAT_STALE_SECONDS", 60
        )

    @property
    def effective_presence_fresh_seconds(self):
        return self._fallback(
            "presence_fresh_seconds", "PRESENCE_HEARTBEAT_FRESH_SECONDS", 30
        )

    @property
    def effective_location_max_age_seconds(self):
        return self._fallback(
            "location_max_age_seconds", "MATCHING_LOCATION_MAX_AGE_SECONDS", 60
        )

    @property
    def effective_invitation_reject_cooldown_seconds(self):
        return self._fallback(
            "invitation_reject_cooldown_seconds",
            "RIDE_INVITATION_REJECT_COOLDOWN_SECONDS",
            60,
        )

    @property
    def effective_arrival_radius_m(self):
        return self._fallback("arrival_radius_m", "TRIP_ARRIVAL_RADIUS_M", 200)

    @property
    def effective_dropoff_radius_m(self):
        return self._fallback("dropoff_radius_m", "TRIP_DROPOFF_RADIUS_M", 300)

    # -----------------------------------------------------------------
    # أنصاف الأقطار — تعود float لا Decimal
    #
    # لأنّ مستهلكها الوحيد هو `D(km=...)` وحسابات المسافة، وكلاهما يريد
    # عددًا عشريًّا. إعادة Decimal هنا تعني تحويلًا في كلّ موضع نداء —
    # وموضعًا واحدًا يُنسى فيرفع TypeError في مسار المطابقة الحارّ.
    # -----------------------------------------------------------------

    @property
    def effective_search_radius_options_km(self):
        """خيارات نطاق البحث للزبون: موجبة، مرتّبة، لا تتجاوز نصف قطر المنطقة."""
        ceiling = self.effective_instant_radius_km
        options = set()
        for value in self.search_radius_options_km or []:
            try:
                km = float(value)
            except (TypeError, ValueError):
                continue
            if km > 0:
                options.add(min(km, ceiling))
        return sorted(options)

    @property
    def effective_instant_radius_km(self):
        """نصف قطر الطلب الفوري — الرقم الذي يحدّد مَن يُطابَق."""
        if self.default_matching_radius_km:
            return float(self.default_matching_radius_km)
        from django.conf import settings
        return float(getattr(settings, "MATCHING_NORMAL_RADIUS_KM", 5))

    @property
    def effective_marketplace_radius_km(self):
        """نصف قطر المجدول والمنشور — أوسع من الفوري عمدًا."""
        return float(
            self._fallback(
                "marketplace_radius_km", "MATCHING_MARKETPLACE_RADIUS_KM", 10
            )
        )

    @property
    def effective_shared_join_radius_km(self):
        return float(
            self._fallback(
                "shared_join_radius_km", "MATCHING_SHARED_JOIN_RADIUS_KM", 3
            )
        )

    @property
    def effective_shared_scheduled_pickup_radius_km(self):
        return float(
            self._fallback(
                "shared_scheduled_pickup_radius_km",
                "MATCHING_SHARED_SCHEDULED_PICKUP_RADIUS_KM",
                10,
            )
        )

    @property
    def effective_shared_scheduled_dest_radius_km(self):
        return float(
            self._fallback(
                "shared_scheduled_dest_radius_km",
                "MATCHING_SHARED_SCHEDULED_DEST_RADIUS_KM",
                15,
            )
        )

    @property
    def effective_shared_scheduled_time_window_minutes(self):
        return int(
            self._fallback(
                "shared_scheduled_time_window_minutes",
                "MATCHING_SHARED_SCHEDULED_TIME_WINDOW_MINUTES",
                60,
            )
        )

    # -----------------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------------

    def allows_policy(self, policy):
        return policy in self.effective_pricing_policies

    def allows_invitation_for_mode(self, mode):
        return mode in self.effective_invitation_modes

    def is_valid_invitation_ttl(self, seconds):
        try:
            return int(seconds) in self.effective_ttl_options
        except (TypeError, ValueError):
            return False
