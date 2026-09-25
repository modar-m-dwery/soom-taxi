from decimal import Decimal, ROUND_HALF_UP


class PricingPolicyError(Exception):
    """سعر مقترح يخالف خطة التسعير المفعّلة في منطقة الخدمة."""
    pass


ONE = Decimal("1")
CENT = Decimal("0.01")


def _d(value):
    """تحويل آمن إلى Decimal (يتفادى أخطاء float الشهيرة في المال)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value):
    return _d(value).quantize(CENT, rounding=ROUND_HALF_UP)


class PricingService:
    """
    محرّك التسعير، واعٍ بخطة التسعير المفعّلة في منطقة الخدمة.

    البنية:
        quote()                 -> يحسب التسعيرة المرجعية + حدودها القانونية
        validate_proposed_fare()-> البوابة الوحيدة التي تقرر: هل هذا السعر مسموح؟

    كل مسار يدخل منه سعر إلى النظام (عرض سائق، اقتراح زبون، سعر مضاد في
    دعوة مباشرة) يجب أن يمرّ عبر validate_proposed_fare. وجود بوابة واحدة
    هو ما يجعل الامتثال قابلًا للإثبات بدل أن يكون موزّعًا على عشرة أماكن.
    """

    # -----------------------------------------------------------------
    # جداول الأساس (تبقى كما هي - لم نغيّر أي رقم)
    # -----------------------------------------------------------------

    BASE_FARES = {
        "fast": Decimal("5000"),
        "express": Decimal("6000"),
        "standard": Decimal("4000"),
        "saving": Decimal("3000"),
        "shared": Decimal("2500"),
        "scheduled": Decimal("4500"),
    }

    PER_KM = {
        "fast": Decimal("1000"),
        "express": Decimal("1200"),
        "standard": Decimal("800"),
        "saving": Decimal("600"),
        "shared": Decimal("500"),
        "scheduled": Decimal("900"),
    }

    PER_MINUTE = {
        "fast": Decimal("100"),
        "express": Decimal("120"),
        "standard": Decimal("80"),
        "saving": Decimal("60"),
        "shared": Decimal("50"),
        "scheduled": Decimal("90"),
    }

    # قرار MVP: لا عمولة إطلاقًا. الحقل باقٍ في التصميم لأي نموذج لاحق.
    PLATFORM_FEE = Decimal("0")

    # =================================================================
    # الواجهة القديمة - محفوظة كما هي حتى لا يُكسر أي كود قائم
    # =================================================================

    @classmethod
    def calculate_base_fare(cls, mode, distance_km, duration_minutes):
        """
        الواجهة التي يستدعيها RideRequestService اليوم. تعمل تمامًا كما كانت
        (بلا منطقة خدمة = بلا قيود إضافية)، لكنها الآن غلاف حول quote()
        حتى لا يوجد حسابان مختلفان للسعر في المشروع.
        """
        return cls.quote(
            mode=mode,
            distance_km=distance_km,
            duration_minutes=duration_minutes,
        )

    # =================================================================
    # الحساب الكامل
    # =================================================================

    @classmethod
    def quote(
        cls,
        mode,
        distance_km,
        duration_minutes,
        service_area=None,
        policy=None,
        surge_multiplier=None,
        regulator_surcharge=None,
    ):
        """
        يرجّع التسعيرة المرجعية مع الحدود القانونية المشتقّة من إعدادات
        المنطقة. المفاتيح القديمة السبعة موجودة كلها بنفس أسمائها.
        """
        if mode not in cls.BASE_FARES:
            raise PricingPolicyError(f"نمط خدمة غير معروف: {mode}")

        base = cls.BASE_FARES[mode]
        distance_charge = _d(distance_km) * cls.PER_KM[mode]
        time_charge = _d(duration_minutes) * cls.PER_MINUTE[mode]

        gross = base + distance_charge + time_charge

        # -------------------------------------------------------------
        # التسعير الديناميكي
        # -------------------------------------------------------------
        effective_surge, surge_source = cls._resolve_surge(
            service_area, surge_multiplier
        )
        gross = gross * effective_surge

        # نوافذ الهيئة (دبي): ليست مضاعِفًا بل رسم ثابت تحدده الجهة المنظِّمة.
        surcharge = _d(regulator_surcharge or 0)
        if surcharge and cls._surge_mode(service_area) == "regulator_tiers":
            gross = gross + surcharge
        else:
            surcharge = Decimal("0")

        # -------------------------------------------------------------
        # الحد الأدنى المطلق (13 درهم في دبي مثلًا)
        # -------------------------------------------------------------
        min_fare = cls._min_fare_absolute(service_area)
        min_fare_applied = False

        if min_fare is not None and gross < min_fare:
            gross = min_fare
            min_fare_applied = True

        gross = _money(gross)

        # -------------------------------------------------------------
        # ممر التعرفة
        # -------------------------------------------------------------
        active_policy = cls.resolve_policy(service_area, policy)
        fare_floor, fare_cap = cls._corridor(service_area, gross, active_policy)

        # -------------------------------------------------------------
        # العمولة وصافي السائق
        # -------------------------------------------------------------
        from catalog.services import Catalog

        platform_fee = cls._platform_fee(
            service_area, gross, service=Catalog.service_for_mode(mode) or "taxi",
        )
        driver_net = _money(gross - platform_fee)
        customer_total = _money(gross)

        return {
            # المفاتيح السبعة الأصلية - لم يتغيّر اسم ولا معنى أيٍّ منها
            "base_fare": _money(base),
            "distance_fare": _money(distance_charge),
            "time_fare": _money(time_charge),
            "gross_fare": gross,
            "platform_fee": platform_fee,
            "customer_total": customer_total,
            "driver_net": driver_net,
            # الإضافات الجديدة
            "pricing_policy": active_policy,
            "fare_floor": fare_floor,
            "fare_cap": fare_cap,
            "surge_multiplier": effective_surge,
            "surge_source": surge_source,
            "regulator_surcharge": _money(surcharge),
            "min_fare_applied": min_fare_applied,
            "currency": getattr(service_area, "currency_code", None) or "SYP",
        }

    # =================================================================
    # البوابة: هل هذا السعر المقترح مسموح؟
    # =================================================================

    @classmethod
    def validate_proposed_fare(
        cls,
        proposed_fare,
        quote,
        service_area=None,
        policy=None,
        proposer="driver",
    ):
        """
        proposed_fare : السعر الذي اقترحه السائق أو الزبون
        quote         : ناتج quote() لنفس الرحلة (المرجع القانوني)
        proposer      : "driver" أو "customer" - يحدد أي خطة تُطبَّق

        يرفع PricingPolicyError برسالة عربية واضحة، أو يرجّع Decimal مُطبَّعًا.
        """
        proposed = _money(proposed_fare)

        if proposed <= 0:
            raise PricingPolicyError("السعر يجب أن يكون أكبر من صفر.")

        active_policy = policy or quote.get("pricing_policy") or cls.resolve_policy(
            service_area, None
        )

        # -------------------------------------------------------------
        # 1) هل الخطة مفعّلة أصلًا في هذه المنطقة؟
        # -------------------------------------------------------------
        if service_area is not None and not service_area.allows_policy(active_policy):
            raise PricingPolicyError(
                f"خطة التسعير '{active_policy}' غير مفعّلة في {service_area.name}."
            )

        # -------------------------------------------------------------
        # 2) الخطط التي لا تقبل أي سعر مقترح إطلاقًا
        # -------------------------------------------------------------
        if active_policy in ("platform_fixed", "regulated_tariff"):
            if proposed != quote["gross_fare"]:
                label = (
                    "تعرفة رسمية إلزامية"
                    if active_policy == "regulated_tariff"
                    else "سعر ثابت من المنصة"
                )
                raise PricingPolicyError(
                    f"{label}: السعر غير قابل للتعديل. "
                    f"القيمة المطلوبة {quote['gross_fare']}."
                )
            return proposed

        # -------------------------------------------------------------
        # 3) من يحقّ له الاقتراح؟
        # -------------------------------------------------------------
        if active_policy == "driver_bidding" and proposer != "driver":
            raise PricingPolicyError("في هذه المنطقة السائق وحده من يقترح السعر.")

        if active_policy == "customer_bidding" and proposer not in ("customer", "driver"):
            raise PricingPolicyError("مُقترِح غير معروف.")

        # -------------------------------------------------------------
        # 4) الحدود: الممر ثم الحد الأدنى المطلق
        # -------------------------------------------------------------
        floor = quote.get("fare_floor")
        cap = quote.get("fare_cap")

        if floor is not None and proposed < floor:
            raise PricingPolicyError(
                f"السعر أقل من الحد المسموح ({floor} {quote.get('currency', '')})."
            )

        if cap is not None and proposed > cap:
            raise PricingPolicyError(
                f"السعر أعلى من الحد المسموح ({cap} {quote.get('currency', '')})."
            )

        min_fare = cls._min_fare_absolute(service_area)
        if min_fare is not None and proposed < min_fare:
            raise PricingPolicyError(
                f"الحد الأدنى للأجرة في هذه المنطقة هو {min_fare}."
            )

        # -------------------------------------------------------------
        # 5) حصة السائق الدنيا (الهند: ≥80%)
        # -------------------------------------------------------------
        min_share = getattr(service_area, "driver_min_share_pct", None)
        if min_share:
            fee = cls._platform_fee(service_area, proposed)
            if (proposed - fee) < (proposed * _d(min_share) / 100):
                raise PricingPolicyError(
                    f"صافي السائق يجب ألّا يقل عن {min_share}% من الأجرة."
                )

        return proposed

    @classmethod
    def settle_from_offer(cls, ride, offer, driver):
        """
        يعيد كتابة لقطة الأجرة في الطلب من العرض الفائز.

        الطلب يُسعَّر عند الإنشاء بتقدير (المسافة والزمن)، ثمّ يعرض السائق
        سعره ويختاره الزبون. قبل هذا التابع بقي `customer_total` على
        التقدير، فكانت الدفعة تُفتح بـ5,136 لعرضٍ قُبل بـ6,000 — والتطبيقان
        يعرضان التقدير. «السعر الذي تختاره هو الذي تدفعه» يُنفَّذ هنا.
        """
        from growth.services.commission import CommissionService

        gross = _money(_d(offer.gross_fare))
        fee = cls._platform_fee(
            ride.service_area, gross, driver=driver,
            service=CommissionService.service_for_ride(ride),
        )
        ride.gross_fare = gross
        ride.platform_fee = fee
        ride.driver_net = _money(gross - fee)
        ride.customer_total = gross
        return ["gross_fare", "platform_fee", "driver_net", "customer_total"]

    # =================================================================
    # HELPERS
    # =================================================================

    @staticmethod
    def resolve_policy(service_area, requested_policy=None):
        if requested_policy:
            return requested_policy
        if service_area is not None and service_area.default_pricing_policy:
            return service_area.default_pricing_policy
        return "platform_fixed"

    @staticmethod
    def _surge_mode(service_area):
        return getattr(service_area, "surge_mode", None) or "disabled"

    @classmethod
    def _resolve_surge(cls, service_area, requested):
        """
        يرجّع (المضاعِف الفعلي، مصدره). المصدر مهم للتدقيق: مضاعِف حسبته
        المنصة ومضاعِف فرضته الجهة المنظِّمة ليسا الشيء نفسه أمام المراجع.
        """
        mode = cls._surge_mode(service_area)

        if mode == "disabled" or requested is None:
            return ONE, "none"

        requested = _d(requested)

        if requested < ONE:
            requested = ONE

        if mode == "capped":
            cap = getattr(service_area, "surge_max_multiplier", None)
            if cap is not None:
                return min(requested, _d(cap)), "platform_capped"
            return requested, "platform_capped"

        if mode == "regulator_tiers":
            # المنصة لا تحسب مضاعِفًا هنا؛ الزيادة تأتي كرسم ثابت من الهيئة.
            return ONE, "regulator"

        return requested, "platform_free"

    @staticmethod
    def _min_fare_absolute(service_area):
        value = getattr(service_area, "min_fare_absolute", None)
        return _money(value) if value is not None else None

    @classmethod
    def _corridor(cls, service_area, gross, policy):
        """
        الأرضية والسقف. يُطبَّقان في ممر التعرفة، وكذلك في المزايدة إن كان
        الأدمن قد ضبط مضاعفات (كثير من الدول تسمح بالمزايدة لكن ضمن حدود).
        """
        if service_area is None:
            return None, None

        floor_mult = getattr(service_area, "fare_floor_multiplier", None)
        cap_mult = getattr(service_area, "fare_cap_multiplier", None)

        applies = policy in ("tariff_corridor", "driver_bidding", "customer_bidding")

        if not applies:
            return None, None

        floor = _money(gross * _d(floor_mult)) if floor_mult is not None else None
        cap = _money(gross * _d(cap_mult)) if cap_mult is not None else None

        min_fare = cls._min_fare_absolute(service_area)
        if min_fare is not None:
            floor = min_fare if floor is None else max(floor, min_fare)

        return floor, cap

    @classmethod
    def _platform_fee(cls, service_area, gross, driver=None, service=None):
        """
        MVP: صفر دائمًا. لكن السقف مطبَّق مسبقًا حتى لا يُنسى يوم تُفعَّل
        العمولة - إندونيسيا 15% وكينيا 18% سقوف قانونية لا تفضيلات.

        السائق المؤسّس (commission_exempt) معفًى دائمًا — وعدٌ موقَّع في ورقة
        المؤسّس، يُنفَّذ هنا لا في العقود.
        """
        if driver is not None and getattr(driver, "commission_exempt", False):
            return _money(Decimal("0"))

        # قواعد العمولة من الأدمن (growth.CommissionRule): سائق ← مجموعة ←
        # مدينة ← عامّة. بلا سائق (تقدير عند الإنشاء) تنطبق المدينة/العامّة.
        from growth.services.commission import CommissionService

        fee = max(
            _d(cls.PLATFORM_FEE),
            CommissionService.fee_for(driver, service_area, gross, service=service),
        )

        cap_pct = getattr(service_area, "commission_cap_pct", None)
        if cap_pct is not None:
            fee = min(fee, _money(_d(gross) * _d(cap_pct) / 100))

        return _money(fee)
