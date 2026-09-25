"""
مخطّطات نقطة الإعداد.

هذه ليست تمثيلًا لنموذج ServiceArea — بل عقدٌ منفصل عنه عمدًا. الفرق ليس
شكليًّا:

  • النموذج فيه ما لا يخصّ التطبيق: هامش عمولة السائق، اسم الجهة المنظِّمة،
    معايرة التقدير الداخلي. كشفها للعميل تسريبُ أعمالٍ بلا فائدة له.

  • النموذج يقبل NULL بمعنى «استعمل الافتراضي العامّ»، والتطبيق لا يعرف
    الافتراضيات ولا يجب أن يعرفها. لذلك يخرج هنا الرقم المحسوب (effective)
    لا الخام: العميل يقرأ قيمة واحدة صريحة دائمًا.

  • تغيير اسم حقل في النموذج غدًا يجب ألّا يكسر تطبيقًا منشورًا على آلاف
    الأجهزة. الفصل هو ما يجعل ذلك ممكنًا.
"""
from rest_framework import serializers


class AreaTimingsSerializer(serializers.Serializer):
    """المهل التي يبني عليها التطبيق عدّاداته ورسائله."""

    offer_ttl_seconds = serializers.IntegerField(
        help_text="مهلة صلاحية عرض السائق — ابنِ عليها عدّاد بطاقة العرض.",
    )
    ride_search_window_minutes = serializers.IntegerField(
        help_text="كم يبقى الطلب الفوري يبحث قبل أن ينتهي.",
    )
    invitation_ttl_options = serializers.ListField(
        child=serializers.IntegerField(),
        help_text=(
            "المهل المسموح بها للدعوة المباشرة. أرسل واحدة منها حصرًا في "
            "ttl_seconds — أيّ قيمة أخرى تُرفض بـ400."
        ),
    )
    invitation_ttl_default = serializers.IntegerField(
        help_text="المهلة المختارة مسبقًا في واجهة الدعوة.",
    )
    invitation_max_parallel = serializers.IntegerField(
        help_text="كم دعوة معلّقة يسمح بها الطلب الواحد في هذه المدينة.",
    )
    auto_dispatch_ttl_seconds = serializers.IntegerField(required=False)

    cancel_free_window_seconds = serializers.IntegerField(required=False)

    cancel_driver_late_grace_minutes = serializers.IntegerField(required=False)

    cancel_wait_minutes = serializers.IntegerField(
        required=False,
        help_text=(
            "بعد وصول السائق وانتظاره هذه الدقائق: إلغاء الزبون مخالفتان، "
            "ويستطيع السائق تسجيل «الزبون لم يحضر»."
        ),
    )

    late_cancel_strike_limit = serializers.IntegerField(required=False)

    auto_dispatch_max_attempts = serializers.IntegerField(required=False)

    invitation_reject_cooldown_seconds = serializers.IntegerField(
        help_text="بعد رفض سائق، كم ثانية يبقى مخفيًّا عن هذا الزبون.",
    )
    presence_stale_seconds = serializers.IntegerField(
        help_text=(
            "انقطاع النبض هذه المدّة يُخرج السائق من الأسطول المرئي. "
            "أرسل النبض بوتيرة أعلى من ثُلثها."
        ),
    )
    presence_fresh_seconds = serializers.IntegerField(
        help_text="أقصى عمر للنبض ليُعدّ السائق حاضرًا لا متأخّرًا.",
    )
    location_max_age_seconds = serializers.IntegerField(
        help_text="أقصى عمر لموقع السائق ليدخل المطابقة.",
    )


class AreaGeometrySerializer(serializers.Serializer):
    """الأرقام المكانية التي تحكم شاشات الخريطة."""

    matching_radius_km = serializers.FloatField(
        help_text=(
            "نصف قطر البحث للطلب الفوري — نفس الرقم الذي يفلتر السائقين "
            "على الخادم. ارسم به دائرة البحث ولا تُثبّت قيمة في التطبيق."
        ),
    )
    marketplace_radius_km = serializers.FloatField(
        help_text="نصف قطر الطلبات المجدولة والرحلات المنشورة.",
    )
    shared_join_radius_km = serializers.FloatField(
        help_text="أقصى مسافة بين نقطتَي التقاط في المشاركة الفورية.",
    )
    shared_scheduled_pickup_radius_km = serializers.FloatField(
        help_text="نطاق التقاط المشاركة المجدولة.",
    )
    shared_scheduled_dest_radius_km = serializers.FloatField(
        help_text="نطاق توافق الوجهة في المشاركة المجدولة.",
    )
    shared_scheduled_time_window_minutes = serializers.IntegerField(
        help_text="فرق الوقت المقبول بين رحلتين مجدولتين لتُعدّا متوافقتين.",
    )
    arrival_radius_m = serializers.IntegerField(
        help_text=(
            "كم مترًا يُقبل لتسجيل «وصلت». اعرضه للسائق قبل أن يردّ الخادم "
            "بـ400 لا بعده."
        ),
    )
    dropoff_radius_m = serializers.IntegerField(
        help_text="أبعد من هذا عن الوجهة يُعلَّم الإنهاء للمراجعة.",
    )
    search_radius_options_km = serializers.ListField(
        child=serializers.FloatField(),
        required=False,
        help_text="نطاقات البحث التي يختار منها الزبون. فارغة = لا اختيار.",
    )

    marketplace_cell_precision = serializers.IntegerField(
        help_text="دقّة خلايا geohash — تحدّد حجم غرفة السوق التي تشترك بها.",
    )


class AreaPricingSerializer(serializers.Serializer):
    """ما يحتاجه التطبيق ليعرض السعر بصدق. لا هوامش ولا عمولات."""

    currency_code = serializers.CharField()
    default_policy = serializers.CharField(
        help_text="خطة التسعير المطبَّقة ما لم يُطلب غيرها.",
    )
    allowed_policies = serializers.ListField(child=serializers.CharField())
    surge_enabled = serializers.BooleanField(
        help_text="هل قد يظهر مضاعف ازدحام في هذه المدينة أصلًا.",
    )
    surge_max_multiplier = serializers.CharField(
        allow_null=True,
        help_text="سقف المضاعف إن كان مفعّلًا بسقف.",
    )
    min_fare_absolute = serializers.CharField(allow_null=True)
    first_ride_discount_pct = serializers.CharField(
        help_text="نسبة خصم أوّل مشوار للزبون الجديد — «0» إن كان معطَّلًا.",
    )
    first_ride_discount_cap = serializers.CharField(
        allow_null=True, help_text="سقف الخصم بالعملة المحلّية.",
    )
    referral_reward = serializers.CharField(
        help_text="رصيد الإحالة للداعي والمدعوّ بعد أوّل رحلة — «0» إن كان معطَّلًا.",
    )
    customer_can_propose = serializers.BooleanField(
        required=False,
        help_text="هل يعرض الزبون سعره في «سوم» هنا (خطّة customer_bidding).",
    )
    customer_proposal_min_ratio = serializers.CharField(
        required=False,
        help_text="أدنى سعر يقترحه الزبون كنسبة من تسعيرة المنصّة.",
    )
    customer_proposal_counter_ratio = serializers.CharField(
        required=False,
        help_text="أعلى عرض للسائق كنسبة من سعر الزبون.",
    )
    customer_proposal_step = serializers.CharField(
        required=False,
        help_text="خطوة زرّي − و+ بعملة المنطقة.",
    )


class MapTilesSerializer(serializers.Serializer):
    """مزوّد بلاطات الخريطة — يتبدّل من الخادم بلا تحديث للتطبيق."""

    url_template = serializers.CharField(
        help_text="رابط البلاطات بـ{z} و{x} و{y}، ومعه مفتاح المزوّد إن لزم.",
    )
    dark_url_template = serializers.CharField(
        allow_null=True, help_text="نسخة الوضع الليليّ — null = الرابط نفسه.",
    )
    attribution = serializers.CharField(help_text="نصّ الحقوق الذي يشترطه المزوّد.")
    max_zoom = serializers.IntegerField()


class VehicleCategorySerializer(serializers.Serializer):
    """فئة مركبة كما يعرضها التطبيق في قائمة الاختيار."""

    code = serializers.CharField(
        help_text="الرمز الثابت — أرسله في requested_vehicle_type.",
    )
    name = serializers.CharField(help_text="الاسم للعرض.")
    seats = serializers.IntegerField(help_text="عدد الركّاب المعتاد.")
    sort_order = serializers.IntegerField()


class AppConfigSerializer(serializers.Serializer):
    """
    كلّ ما يحتاج التطبيق معرفته عن المدينة التي يقف فيها المستخدم.

    القاعدة التي يجب أن يتبعها العميل: اقرأ هذه النقطة عند الإقلاع واخزنها،
    ولا تُثبّت أيًّا من أرقامها في الشيفرة. تغييرها من الأدمن يسري فورًا،
    وتطبيقٌ يحمل نسخته الخاصّة من الأرقام سيتصرّف بقواعد مدينةٍ لم تعد
    قائمة — ويُرفض طلبه برسالة لا يفهمها المستخدم.
    """

    area_code = serializers.CharField(allow_null=True)
    area_name = serializers.CharField(allow_null=True)
    country_code = serializers.CharField(allow_null=True)
    resolved_from = serializers.CharField(
        help_text=(
            "كيف حُدِّدت المنطقة: coordinates إن أرسلت إحداثيات، code إن "
            "سمّيت المنطقة، default إن أُخذت الأولى، أو none إن لم تُحلّ."
        ),
    )

    ride_modes = serializers.ListField(
        child=serializers.CharField(),
        help_text="درجات الخدمة المتاحة هنا.",
    )
    invitation_allowed_modes = serializers.ListField(
        child=serializers.CharField(),
        help_text="الدرجات التي تعمل معها الدعوة المباشرة في هذه المدينة.",
    )
    vehicle_categories = VehicleCategorySerializer(many=True)
    services = serializers.ListField(
        child=serializers.DictField(),
        help_text="الخدمات الظاهرة هنا: code, name, name_en, icon, description, status (active|coming_soon), sort_order.",
    )
    features = serializers.DictField(
        child=serializers.BooleanField(),
        help_text="مفاتيح الميزات: nearest, pick_car, search_radius, scheduled_rides, referral…",
    )
    trip_categories = serializers.ListField(
        child=serializers.CharField(),
        help_text="أنواع الرحلة المتاحة هنا (city دائمًا).",
    )

    timings = AreaTimingsSerializer()
    geometry = AreaGeometrySerializer()
    pricing = AreaPricingSerializer()
    map_tiles = MapTilesSerializer(required=False)

    server_time = serializers.DateTimeField(
        help_text=(
            "وقت الخادم عند الردّ. قارِنه بساعة الجهاز: انحرافٌ كبير يفسّر "
            "عدّادات تنتهي مبكّرًا أو متأخّرًا، وهو أوّل ما يجب فحصه."
        ),
    )
