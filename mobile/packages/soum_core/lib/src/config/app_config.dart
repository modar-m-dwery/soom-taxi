/// إعداد المدينة — أوّل نداء يقوم به التطبيق، وقبل تسجيل الدخول.
///
/// §0.1 في دليل التكامل: «هذه النقطة أهمّ من نقطة تسجيل الدخول، واقرأها
/// قبلها». والسبب ليس ترتيبًا شكليًّا:
///
/// > كلّ رقم في المنصّة — مهل العدّادات، أنصاف الأقطار، فئات المركبات، خطط
/// > التسعير — يضبطه المشغّل لكلّ مدينة من لوحة الإدارة، ويسري فورًا بلا
/// > نشر. لا تُثبّت أيًّا منها في الشيفرة: مشغّلٌ يغيّر مهلة الدعوة يجعل
/// > تطبيقك يرسل قيمة يرفضها الخادم، والمستخدم يقرأ خطأً لا ذنب له فيه،
/// > ولا يُصلَح ذلك إلّا بإصدار جديد على المتجر.
///
/// لذلك: لا رقم من هذا الملفّ مكتوب في أيّ مكان آخر في المشروع.
library;

import 'package:equatable/equatable.dart';

import '../models/fare_proposal.dart';
import '../models/json.dart';
import 'server_clock.dart';

/// كيف حُلّت المدينة — ودرجة الثقة بالنتيجة (§0.1).
enum AreaResolution {
  /// من موقع المستخدم. أدقّ حالة.
  coordinates('coordinates'),

  /// سمّيت المدينة بالرمز.
  ///
  /// الاسم `byCode` لا `code`: عضوٌ باسم حقلِ التعداد نفسه تعارضٌ في Dart.
  byCode('code'),

  /// لم يُرسَل شيء، فأُخذت أوّل مدينة فعّالة. أعد النداء بعد إذن الموقع.
  byDefault('default'),

  /// المستخدم خارج كلّ منطقة خدمة. الأرقام العامّة تعود كاملة لترسم
  /// شاشة، لكن لا يُعرض له أنّه في مدينة ليس فيها.
  none('none'),

  unknown('unknown');

  const AreaResolution(this.code);
  final String code;

  static AreaResolution from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => AreaResolution.unknown,
      );

  /// هل نعرض اسم المدينة للمستخدم؟
  bool get isTrustworthy =>
      this == AreaResolution.coordinates || this == AreaResolution.byCode;
}

class VehicleCategoryOption extends Equatable {
  const VehicleCategoryOption({
    required this.code,
    required this.name,
    required this.seats,
    required this.sortOrder,
  });

  final String code;
  final String name;
  final int seats;
  final int sortOrder;

  factory VehicleCategoryOption.fromJson(Json json) => VehicleCategoryOption(
        code: readString(json, 'code'),
        name: readString(json, 'name'),
        seats: readInt(json, 'seats', fallback: 4),
        sortOrder: readInt(json, 'sort_order', fallback: 100),
      );

  Json toJson() => {
        'code': code,
        'name': name,
        'seats': seats,
        'sort_order': sortOrder,
      };

  @override
  List<Object?> get props => [code, name, seats, sortOrder];
}

class AreaTimings extends Equatable {
  const AreaTimings({
    required this.offerTtlSeconds,
    required this.rideSearchWindowMinutes,
    required this.invitationTtlOptions,
    required this.invitationTtlDefault,
    required this.invitationMaxParallel,
    required this.invitationRejectCooldownSeconds,
    required this.presenceStaleSeconds,
    required this.presenceFreshSeconds,
    required this.locationMaxAgeSeconds,
    this.cancelFreeWindowSeconds = 120,
    this.cancelDriverLateGraceMinutes = 5,
    this.cancelWaitMinutes = 5,
    this.lateCancelStrikeLimit = 3,
  });

  /// سياسة الإلغاء: التطبيق يقول للزبون قبل التأكيد هل إلغاؤه مجّانيّ.
  final int cancelFreeWindowSeconds;
  final int cancelDriverLateGraceMinutes;
  final int lateCancelStrikeLimit;

  /// بعد وصول السائق وانتظاره هذه الدقائق يستطيع تسجيل «الزبون لم يحضر».
  final int cancelWaitMinutes;

  /// عدّاد بطاقة العرض.
  final int offerTtlSeconds;

  /// عدّاد شاشة البحث.
  final int rideSearchWindowMinutes;

  /// المهل المسموح بها للدعوة. أيّ قيمة خارجها تُرفض بـ400 (§5.1).
  final List<int> invitationTtlOptions;
  final int invitationTtlDefault;

  /// كم دعوة معلّقة يسمح بها الخادم في وقت واحد.
  final int invitationMaxParallel;

  /// بعد رفض سائق، لا يُعاد دعوته قبل انقضاء هذه المدّة.
  final int invitationRejectCooldownSeconds;

  /// §12.3: مهلة الانقطاع تُقرأ من هنا لا من الرقم 60.
  final int presenceStaleSeconds;
  final int presenceFreshSeconds;
  final int locationMaxAgeSeconds;

  /// وتيرة نبض الموقع.
  ///
  /// §6.2 يحدّدها صراحةً: «كل 3–5 ثوانٍ». وهي ليست اختيارًا حرًّا داخل
  /// هذا المدى، بل يحكمها قيدان معًا:
  ///
  /// **الحدّ الأعلى** من الخادم: `DriverRoomConsumer` يكتب الموقع إلى
  /// القاعدة كلّ خمس ثوانٍ على الأكثر، وكلّ فحص جغرافيّ يقرأ من القاعدة.
  /// نبضٌ أبطأ من ذلك يجعل «وصلت» تُقاس على موقع أقدم بلا داعٍ.
  ///
  /// **الحدّ الأدنى** من البطارية والشبكة: نبضٌ كلّ ثانية يستنزف الاثنتين
  /// بلا أن يضيف دقّة يلاحظها أحد.
  ///
  /// ونُبقيها دون ثلث `presence_stale_seconds` أيضًا، فيبقى هامش ثلاث
  /// محاولات قبل أن يكنس الخادمُ السائقَ عند تعثّر شبكة.
  Duration get heartbeatInterval {
    final byStaleness = (presenceStaleSeconds / 4).floor();
    final seconds = byStaleness.clamp(3, 5);
    return Duration(seconds: seconds);
  }

  factory AreaTimings.fromJson(Json json) => AreaTimings(
        offerTtlSeconds: readInt(json, 'offer_ttl_seconds', fallback: 90),
        rideSearchWindowMinutes:
            readInt(json, 'ride_search_window_minutes', fallback: 10),
        invitationTtlOptions: readIntList(json, 'invitation_ttl_options'),
        invitationTtlDefault: readInt(json, 'invitation_ttl_default', fallback: 20),
        invitationMaxParallel: readInt(json, 'invitation_max_parallel', fallback: 1),
        invitationRejectCooldownSeconds:
            readInt(json, 'invitation_reject_cooldown_seconds', fallback: 60),
        presenceStaleSeconds: readInt(json, 'presence_stale_seconds', fallback: 60),
        presenceFreshSeconds: readInt(json, 'presence_fresh_seconds', fallback: 30),
        locationMaxAgeSeconds:
            readInt(json, 'location_max_age_seconds', fallback: 60),
        cancelFreeWindowSeconds:
            readInt(json, 'cancel_free_window_seconds', fallback: 120),
        cancelDriverLateGraceMinutes:
            readInt(json, 'cancel_driver_late_grace_minutes', fallback: 5),
        cancelWaitMinutes: readInt(json, 'cancel_wait_minutes', fallback: 5),
        lateCancelStrikeLimit:
            readInt(json, 'late_cancel_strike_limit', fallback: 3),
      );

  Json toJson() => {
        'offer_ttl_seconds': offerTtlSeconds,
        'ride_search_window_minutes': rideSearchWindowMinutes,
        'invitation_ttl_options': invitationTtlOptions,
        'invitation_ttl_default': invitationTtlDefault,
        'invitation_max_parallel': invitationMaxParallel,
        'invitation_reject_cooldown_seconds': invitationRejectCooldownSeconds,
        'presence_stale_seconds': presenceStaleSeconds,
        'presence_fresh_seconds': presenceFreshSeconds,
        'location_max_age_seconds': locationMaxAgeSeconds,
        'cancel_free_window_seconds': cancelFreeWindowSeconds,
        'cancel_driver_late_grace_minutes': cancelDriverLateGraceMinutes,
        'cancel_wait_minutes': cancelWaitMinutes,
        'late_cancel_strike_limit': lateCancelStrikeLimit,
      };

  @override
  List<Object?> get props => [
        offerTtlSeconds,
        rideSearchWindowMinutes,
        invitationTtlOptions,
        invitationTtlDefault,
        invitationMaxParallel,
        presenceStaleSeconds,
      ];
}

class AreaGeometry extends Equatable {
  const AreaGeometry({
    required this.matchingRadiusKm,
    required this.marketplaceRadiusKm,
    required this.sharedJoinRadiusKm,
    required this.sharedScheduledPickupRadiusKm,
    required this.sharedScheduledDestRadiusKm,
    required this.sharedScheduledTimeWindowMinutes,
    required this.arrivalRadiusM,
    required this.dropoffRadiusM,
    required this.marketplaceCellPrecision,
    this.searchRadiusOptionsKm = const [],
  });

  /// §0.1: «ليس رقمًا للعرض فقط — هو بالضبط نصف القطر الذي يقرّر مَن
  /// يُطابَق ومَن لا». به تُرسم دائرة البحث، وعليه تُبنى رسالة «لا سيارات
  /// في نطاقك»، فتكون الشاشة صادقة مع الخادم بلا تخمين.
  final double matchingRadiusKm;

  final double marketplaceRadiusKm;
  final double sharedJoinRadiusKm;
  final double sharedScheduledPickupRadiusKm;
  final double sharedScheduledDestRadiusKm;
  final int sharedScheduledTimeWindowMinutes;

  /// «وصلت» تُرفض خارج هذا النطاق. يُعرض للسائق قبل أن يردّ الخادم 400.
  final int arrivalRadiusM;

  /// «أنهيت» — أوسع عمدًا لأنّ الوجهة قد تتغيّر قليلًا بطلب الراكب.
  final int dropoffRadiusM;

  final int marketplaceCellPrecision;

  /// نطاقات البحث التي يختار منها الزبون، من المشغّل لكلّ منطقة. فارغة =
  /// لا اختيار، ونصف قطر المنطقة هو النطاق.
  final List<double> searchRadiusOptionsKm;

  factory AreaGeometry.fromJson(Json json) => AreaGeometry(
        matchingRadiusKm: readDouble(json, 'matching_radius_km', fallback: 5),
        marketplaceRadiusKm:
            readDouble(json, 'marketplace_radius_km', fallback: 10),
        sharedJoinRadiusKm: readDouble(json, 'shared_join_radius_km', fallback: 3),
        sharedScheduledPickupRadiusKm:
            readDouble(json, 'shared_scheduled_pickup_radius_km', fallback: 10),
        sharedScheduledDestRadiusKm:
            readDouble(json, 'shared_scheduled_dest_radius_km', fallback: 15),
        sharedScheduledTimeWindowMinutes:
            readInt(json, 'shared_scheduled_time_window_minutes', fallback: 60),
        arrivalRadiusM: readInt(json, 'arrival_radius_m', fallback: 200),
        dropoffRadiusM: readInt(json, 'dropoff_radius_m', fallback: 300),
        marketplaceCellPrecision:
            readInt(json, 'marketplace_cell_precision', fallback: 7),
        searchRadiusOptionsKm: [
          for (final value in (json['search_radius_options_km'] as List?) ?? const [])
            if (value is num && value > 0) value.toDouble(),
        ],
      );

  Json toJson() => {
        'matching_radius_km': matchingRadiusKm,
        'marketplace_radius_km': marketplaceRadiusKm,
        'shared_join_radius_km': sharedJoinRadiusKm,
        'shared_scheduled_pickup_radius_km': sharedScheduledPickupRadiusKm,
        'shared_scheduled_dest_radius_km': sharedScheduledDestRadiusKm,
        'shared_scheduled_time_window_minutes': sharedScheduledTimeWindowMinutes,
        'arrival_radius_m': arrivalRadiusM,
        'dropoff_radius_m': dropoffRadiusM,
        'marketplace_cell_precision': marketplaceCellPrecision,
        'search_radius_options_km': searchRadiusOptionsKm,
      };

  @override
  List<Object?> get props =>
      [
        matchingRadiusKm,
        marketplaceRadiusKm,
        arrivalRadiusM,
        dropoffRadiusM,
        searchRadiusOptionsKm,
      ];
}

class AreaPricing extends Equatable {
  const AreaPricing({
    required this.currencyCode,
    required this.defaultPolicy,
    required this.allowedPolicies,
    required this.surgeEnabled,
    this.surgeMaxMultiplier,
    this.minFareAbsolute,
    this.customerCanPropose = false,
    FareProposalRules? proposalRules,
  }) : proposalRulesOrNull = proposalRules;

  /// «سوم» بنمط inDrive مفعّل هنا: الزبون يعرض سعره.
  final bool customerCanPropose;
  /// null = افتراضات الخادم (القواعد ليست ثابتة وقت الترجمة فلا تكون
  /// قيمةً افتراضيّة للمُنشئ).
  final FareProposalRules? proposalRulesOrNull;

  FareProposalRules get proposalRules =>
      proposalRulesOrNull ?? FareProposalRules.defaults;

  final String currencyCode;
  final String defaultPolicy;
  final List<String> allowedPolicies;
  final bool surgeEnabled;
  final String? surgeMaxMultiplier;
  final String? minFareAbsolute;

  bool get allowsBidding => allowedPolicies.contains('driver_bidding');

  factory AreaPricing.fromJson(Json json) => AreaPricing(
        currencyCode: readString(json, 'currency_code', fallback: 'SYP'),
        defaultPolicy: readString(json, 'default_policy',
            fallback: 'platform_fixed'),
        allowedPolicies: readStringList(json, 'allowed_policies'),
        surgeEnabled: readBool(json, 'surge_enabled'),
        surgeMaxMultiplier: readStringOrNull(json, 'surge_max_multiplier'),
        minFareAbsolute: readStringOrNull(json, 'min_fare_absolute'),
        customerCanPropose: readBool(json, 'customer_can_propose'),
        proposalRules: FareProposalRules.fromJson(json),
      );

  Json toJson() => {
        'currency_code': currencyCode,
        'default_policy': defaultPolicy,
        'allowed_policies': allowedPolicies,
        'surge_enabled': surgeEnabled,
        'surge_max_multiplier': surgeMaxMultiplier,
        'min_fare_absolute': minFareAbsolute,
        'customer_can_propose': customerCanPropose,
        ...proposalRules.toJson(),
      };

  @override
  List<Object?> get props => [
        currencyCode,
        defaultPolicy,
        allowedPolicies,
        surgeEnabled,
        customerCanPropose,
        proposalRules,
      ];
}

/// خدمةٌ من كتالوج المشغّل — تكسي، مشترك، سفريات… أو قادمة «قريبًا».
class ServiceInfo extends Equatable {
  const ServiceInfo({
    required this.code,
    required this.name,
    required this.icon,
    required this.status,
    this.nameEn = '',
    this.description = '',
    this.sortOrder = 100,
  });

  final String code;
  final String name;
  final String nameEn;
  final String icon;
  final String description;

  /// `active` أو `coming_soon`. المخفيّة لا تصل أصلًا.
  final String status;
  final int sortOrder;

  bool get isActive => status == 'active';
  bool get isComingSoon => status == 'coming_soon';

  factory ServiceInfo.fromJson(Json json) => ServiceInfo(
        code: readString(json, 'code'),
        name: readString(json, 'name'),
        nameEn: readString(json, 'name_en', fallback: ''),
        icon: readString(json, 'icon', fallback: ''),
        description: readString(json, 'description', fallback: ''),
        status: readString(json, 'status', fallback: 'active'),
        sortOrder: readInt(json, 'sort_order', fallback: 100),
      );

  Json toJson() => {
        'code': code,
        'name': name,
        'name_en': nameEn,
        'icon': icon,
        'description': description,
        'status': status,
        'sort_order': sortOrder,
      };

  @override
  List<Object?> get props => [code, status, sortOrder, name];
}

/// مزوّد بلاطات الخريطة — من الخادم، فيتبدّل بلا تحديث للتطبيق.
///
/// الافتراض خوادم OpenStreetMap العامّة: تكفي للتطوير، وسياسة استخدامها
/// تمنع تطبيقًا تجاريًّا بحجم مدينة — فالإنتاج يضع رابط مزوّده في
/// `MAP_TILES_URL` على الخادم.
class MapTileSource extends Equatable {
  const MapTileSource({
    required this.urlTemplate,
    required this.attribution,
    this.darkUrlTemplate,
    this.maxZoom = 19,
  });

  static const openStreetMap = MapTileSource(
    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors',
  );

  final String urlTemplate;

  /// نسخة الوضع الليليّ إن وفّرها المزوّد — null = الرابط نفسه.
  final String? darkUrlTemplate;

  /// نصّ الحقوق الذي يشترطه المزوّد — يُعرض على الخريطة.
  final String attribution;

  final int maxZoom;

  factory MapTileSource.fromJson(Json json) {
    final url = readString(json, 'url_template');
    if (!url.contains('{z}') || !url.contains('{x}') || !url.contains('{y}')) {
      return openStreetMap;
    }
    return MapTileSource(
      urlTemplate: url,
      darkUrlTemplate: readStringOrNull(json, 'dark_url_template'),
      attribution:
          readString(json, 'attribution', fallback: openStreetMap.attribution),
      maxZoom: readInt(json, 'max_zoom', fallback: 19),
    );
  }

  Json toJson() => {
        'url_template': urlTemplate,
        'dark_url_template': darkUrlTemplate,
        'attribution': attribution,
        'max_zoom': maxZoom,
      };

  @override
  List<Object?> get props => [urlTemplate, darkUrlTemplate, attribution, maxZoom];
}

class AppConfig extends Equatable {
  const AppConfig({
    required this.areaCode,
    required this.areaName,
    required this.countryCode,
    required this.resolution,
    required this.rideModes,
    required this.invitationAllowedModes,
    required this.vehicleCategories,
    required this.timings,
    required this.geometry,
    required this.pricing,
    required this.serverTime,
    required this.fetchedAt,
    this.services = const [],
    this.features = const {},
    this.tripCategories = const ['city', 'intercity', 'service_line'],
    this.mapTiles = MapTileSource.openStreetMap,
  });

  /// بلاطات الخريطة — من الخادم.
  final MapTileSource mapTiles;

  /// الكتالوج كما يراه المشغّل لهذه المدينة — يُبنى منه شريط الخدمات.
  final List<ServiceInfo> services;

  /// مفاتيح الميزات: nearest, pick_car, scheduled_rides…
  final Map<String, bool> features;

  /// أنواع الرحلة المفعّلة هنا (city دائمًا).
  final List<String> tripCategories;

  /// ميزةٌ لا يعرفها الخادم (نسخة أقدم منه) تُعدّ مفعّلة: إطفاءٌ صامت لما
  /// كان يعمل أسوأ من ميزةٍ يرفضها الخادم برسالة واضحة.
  bool feature(String key) => features[key] ?? true;

  /// خدمةٌ غائبة عن الكتالوج = مطفأة؛ وكتالوجٌ فارغ (خادمٌ أقدم) = لا قيود.
  bool serviceActive(String code) {
    if (services.isEmpty) return true;
    return services.any((s) => s.code == code && s.isActive);
  }

  final String? areaCode;
  final String? areaName;
  final String? countryCode;
  final AreaResolution resolution;

  /// §12.3: الأنماط تُبنى من هذه القائمة لا من تعداد في التطبيق.
  final List<String> rideModes;

  /// الأنماط التي تعمل معها الدعوة المباشرة — `fast` و`express` في جبلة.
  final List<String> invitationAllowedModes;

  /// §12.3: فئات المركبات تُبنى من هنا لا من قائمة مكتوبة في التطبيق.
  final List<VehicleCategoryOption> vehicleCategories;

  final AreaTimings timings;
  final AreaGeometry geometry;
  final AreaPricing pricing;

  /// §0.1: «قارِنه بساعة الجهاز». جهازٌ ساعتُه متأخّرة دقيقتين يعرض
  /// عدّادات خاطئة على كلّ شاشة فيها مهلة.
  final DateTime serverTime;

  /// محلّي — لحساب عمر النسخة المخزَّنة.
  final DateTime fetchedAt;

  bool supportsInvitation(String mode) => invitationAllowedModes.contains(mode);

  /// الفارق بين ساعة الجهاز وساعة الخادم وقت القراءة.
  ///
  /// تُطبَّق على كلّ عدّاد: `expires_at` تأتي بساعة الخادم، وطرحُها من
  /// ساعة جهازٍ منحرفة دقيقتين يُنتج عدّادًا يبدأ من قيمة خاطئة أو من صفر.
  Duration get clockSkew => serverTime.difference(fetchedAt);

  /// ساعة مصحَّحة تُبنى عليها كلّ العدّادات في التطبيق.
  ServerClock get clock => ServerClock(clockSkew);

  factory AppConfig.fromJson(Json json, {DateTime? fetchedAt}) => AppConfig(
        areaCode: readStringOrNull(json, 'area_code'),
        areaName: readStringOrNull(json, 'area_name'),
        countryCode: readStringOrNull(json, 'country_code'),
        resolution: AreaResolution.from(readStringOrNull(json, 'resolved_from')),
        rideModes: readStringList(json, 'ride_modes'),
        invitationAllowedModes: readStringList(json, 'invitation_allowed_modes'),
        vehicleCategories: readList(
          json,
          'vehicle_categories',
          VehicleCategoryOption.fromJson,
        ),
        timings: AreaTimings.fromJson(asJson(json['timings'])),
        geometry: AreaGeometry.fromJson(asJson(json['geometry'])),
        pricing: AreaPricing.fromJson(asJson(json['pricing'])),
        serverTime: readDate(json, 'server_time'),
        fetchedAt: fetchedAt ?? DateTime.now(),
        services: readList(json, 'services', ServiceInfo.fromJson),
        features: {
          for (final entry
              in ((json['features'] as Map?) ?? const {}).entries)
            if (entry.value is bool) '${entry.key}': entry.value as bool,
        },
        tripCategories: json['trip_categories'] is List
            ? readStringList(json, 'trip_categories')
            : const ['city', 'intercity', 'service_line'],
        mapTiles: json['map_tiles'] is Map
            ? MapTileSource.fromJson(asJson(json['map_tiles']))
            : MapTileSource.openStreetMap,
      );

  Json toJson() => {
        'area_code': areaCode,
        'area_name': areaName,
        'country_code': countryCode,
        'resolved_from': resolution.code,
        'ride_modes': rideModes,
        'invitation_allowed_modes': invitationAllowedModes,
        'vehicle_categories':
            vehicleCategories.map((e) => e.toJson()).toList(growable: false),
        'timings': timings.toJson(),
        'geometry': geometry.toJson(),
        'pricing': pricing.toJson(),
        'server_time': serverTime.toUtc().toIso8601String(),
        'services': services.map((s) => s.toJson()).toList(growable: false),
        'features': features,
        'trip_categories': tripCategories,
        'map_tiles': mapTiles.toJson(),
      };

  @override
  List<Object?> get props => [
        areaCode,
        resolution,
        rideModes,
        timings,
        geometry,
        pricing,
        services,
        features,
        tripCategories,
        mapTiles,
      ];
}
