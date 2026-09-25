import 'package:decimal/decimal.dart';
import 'package:dio/dio.dart';

import '../models/enums.dart';
import '../models/incentive.dart';
import '../models/json.dart';
import '../models/money.dart';
import '../models/offer.dart';
import '../models/ride.dart';
import '../models/trip.dart';
import '../models/vehicle.dart';
import '../network/api_client.dart';

class DriverDocument {
  const DriverDocument({
    required this.id,
    required this.type,
    required this.status,
    this.expiresAt,
    this.rejectionReason = '',
    this.reviewedAt,
  });

  final int id;
  final DriverDocumentType? type;
  final DocumentStatus status;
  final DateTime? expiresAt;
  final String rejectionReason;
  final DateTime? reviewedAt;

  bool get isExpired =>
      status == DocumentStatus.expired ||
      (expiresAt != null && expiresAt!.isBefore(DateTime.now()));

  factory DriverDocument.fromJson(Json json) => DriverDocument(
        id: readInt(json, 'id'),
        // المفتاح `type` لا `document_type` — تحقّقناه على خادم يعمل.
        type: DriverDocumentType.from(readStringOrNull(json, 'type')),
        status: DocumentStatus.from(readStringOrNull(json, 'status')),
        expiresAt: readDateOrNull(json, 'expires_at'),
        rejectionReason: readString(json, 'rejection_reason'),
        reviewedAt: readDateOrNull(json, 'reviewed_at'),
      );
}

/// رصيد السائق عند المنصّة — صفٌّ لكلّ عملة من `/me/driver-balance/`.
///
/// `total` موجبٌ حين تدين له المنصّة (خصوماتٌ تحمّلتها عن الزبون)، وسالبٌ
/// حين يدين هو بالعمولة. الخادم يردّ **قائمة** لا كائنًا؛ قراءتها كائنًا
/// كانت تُظهر صفرًا دائمًا (وُجد على الهاتف بعد أوّل رحلة مخفَّضة).
class DriverBalance {
  const DriverBalance({
    required this.total,
    required this.currency,
    required this.owesPlatform,
    required this.amountOwedToPlatform,
    required this.lifetimeEarned,
    required this.lifetimeCommission,
  });

  final Money total;
  final String currency;
  final bool owesPlatform;
  final Money amountOwedToPlatform;
  final Money lifetimeEarned;
  final Money lifetimeCommission;

  factory DriverBalance.fromJson(Json json) {
    final currency = readString(json, 'currency', fallback: Money.defaultCurrency);
    return DriverBalance(
      total: readMoney(json, 'net_balance', currency: currency),
      currency: currency,
      owesPlatform: readBool(json, 'owes_platform'),
      amountOwedToPlatform:
          readMoney(json, 'amount_owed_to_platform', currency: currency),
      lifetimeEarned: readMoney(json, 'lifetime_earned', currency: currency),
      lifetimeCommission:
          readMoney(json, 'lifetime_commission', currency: currency),
    );
  }

  static DriverBalance empty([String currency = Money.defaultCurrency]) =>
      DriverBalance(
        total: Money(Decimal.zero, currency),
        currency: currency,
        owesPlatform: false,
        amountOwedToPlatform: Money(Decimal.zero, currency),
        lifetimeEarned: Money(Decimal.zero, currency),
        lifetimeCommission: Money(Decimal.zero, currency),
      );

  /// الخادم يردّ صفًّا لكلّ عملة؛ الليرة أوّلًا، وإلّا الأوّل، وإلّا صفر.
  static DriverBalance fromList(Object? raw) {
    final rows = raw is List
        ? raw.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList()
        : const <Json>[];
    if (rows.isEmpty) {
      return raw is Map
          ? DriverBalance.fromJson(raw.cast<String, dynamic>())
          : DriverBalance.empty();
    }
    final syp = rows.where(
      (r) => readString(r, 'currency') == Money.defaultCurrency,
    );
    return DriverBalance.fromJson(syp.isNotEmpty ? syp.first : rows.first);
  }
}

class DriverApi {
  DriverApi(this._client);

  final ApiClient _client;

  Future<Json> profile() async =>
      asJson(await _client.get<dynamic>('/auth/driver/profile/'));

  // -----------------------------------------------------------------
  // المركبات
  // -----------------------------------------------------------------

  Future<List<Vehicle>> vehicles() async {
    final body = await _client.get<dynamic>('/vehicles/');
    return readResults(body).map(Vehicle.fromJson).toList(growable: false);
  }

  /// `type` رمزٌ من `AppConfig.vehicleCategories` — لا من تعداد في التطبيق.
  Future<Vehicle> registerVehicle({
    required String type,
    required String make,
    required String model,
    required int year,
    required String color,
    required String plateNumber,
    required int seats,
  }) async =>
      Vehicle.fromJson(asJson(await _client.post<dynamic>('/vehicles/', body: {
        'type': type,
        'make': make,
        'model': model,
        'year': year,
        'color': color,
        'plate_number': plateNumber,
        'seats': seats,
      })));

  Future<void> activateVehicle(int id) =>
      _client.post<dynamic>('/vehicles/$id/activate/');

  Future<void> deactivateVehicle(int id) =>
      _client.post<dynamic>('/vehicles/$id/deactivate/');

  // -----------------------------------------------------------------
  // الوثائق
  // -----------------------------------------------------------------

  Future<List<DriverDocument>> documents() async {
    final body = await _client.get<dynamic>('/drivers/documents/');
    return readResults(body).map(DriverDocument.fromJson).toList(growable: false);
  }

  Future<DriverDocument> uploadDocument({
    required DriverDocumentType type,
    required String filePath,
    DateTime? expiresAt,
  }) async {
    final form = FormData.fromMap({
      'type': type.code,
      'file': await MultipartFile.fromFile(filePath),
      if (expiresAt != null)
        'expires_at': expiresAt.toUtc().toIso8601String(),
    });

    return DriverDocument.fromJson(
      asJson(await _client.upload<dynamic>('/drivers/documents/', form)),
    );
  }

  // -----------------------------------------------------------------
  // التشغيل
  // -----------------------------------------------------------------

  /// يردّ 400 بـ`driver.not_eligible` ما لم تكتمل الوثائق الأربع.
  ///
  /// **الإحداثيات هنا لا تصل إلى الخادم.** `DriverGoOnlineView.post` لا
  /// يقرأ جسم الطلب إطلاقًا — مخطّطها `request=None`، وتنادي
  /// `DriverAvailabilityService.go_online(profile)` بلا وسيط موقع. فما
  /// يذكره دليل التكامل في §4.2 من `{lat, lng}` يُتجاهَل بصمت.
  ///
  /// وأثره مقيس: `PresenceService.go_online` يرفض زرع السائق في فهرس
  /// GEO ما لم يكن `last_location_at` حديثًا فعلًا — «سائق أغلق التطبيق
  /// أمس ثم ضغط Go Online اليوم يحمل `current_location` من الأمس».
  /// فالسائق يُقبل «متّصلًا» ولا يدخل المطابقة.
  ///
  /// **الخلاصة المعمارية: قناة موقع السائق واحدة لا اثنتان — نبضة
  /// `location.update` على `/ws/driver/{id}/`.** كلّ فحص جغرافيّ في
  /// المنصّة يقرأ من هناك.
  ///
  /// الوسيطان يبقيان في التوقيع عمدًا: يُرسَلان في الجسم فلا يضرّان اليوم
  /// ويعملان يوم يقرأهما الخادم، ويبقى اسمهما توثيقًا لما **يجب** أن
  /// يُرسَل. لكن لا تبنِ عليهما — ابعث النبضة.
  Future<Json> goOnline({required double lat, required double lng}) async =>
      asJson(await _client.post<dynamic>(
        '/drivers/me/go-online/',
        body: {'lat': lat, 'lng': lng},
      ));

  Future<void> goOffline() => _client.post<dynamic>('/drivers/me/go-offline/');

  // -----------------------------------------------------------------
  // المزاد من جهة السائق
  // -----------------------------------------------------------------

  Future<List<RideRequest>> candidates() async {
    final body = await _client.get<dynamic>('/driver/rides/candidates/');
    return readResults(body).map(RideRequest.fromJson).toList(growable: false);
  }

  Future<RideOffer> submitOffer({
    required int rideId,
    required Money grossFare,
    required int etaMinutes,
  }) async =>
      RideOffer.fromJson(asJson(await _client.post<dynamic>(
        '/driver/rides/$rideId/offers/',
        body: {'gross_fare': grossFare.toApi(), 'eta_minutes': etaMinutes},
      )));

  // -----------------------------------------------------------------
  // تنفيذ الرحلة — الترتيب مفروض من الخادم
  // -----------------------------------------------------------------

  /// يردّ 400 إن كان السائق أبعد من `geometry.arrivalRadiusM`.
  ///
  /// حارسٌ مقصود يمنع «وصلت» من مقعد المنزل: وصولٌ كاذب من بعيد يبدأ
  /// عدّاد عدم حضور الزبون، وهو مدخل احتيال حقيقي.
  ///
  /// **والموقع الذي يُقاس ليس الموقع المرسَل هنا.** `TripService.arrived`
  /// يقرأ `driver.current_location` و`last_location_at` من القاعدة —
  /// أي آخر **نبضة**. الجسم يُتجاهَل كما في `go-online`.
  ///
  /// فالترتيب الصحيح: ابعث نبضة، انتظر `presence.ack`، ثمّ نادِ هذه.
  /// نداؤها بلا ذلك يقيس الحارسَ على موقعٍ قد يكون عمره دقائق.
  ///
  /// ورسالة الرفض تحمل المسافة الدقيقة بالعربية جاهزةً للعرض:
  /// «أنت على بعد 340 مترًا من نقطة الالتقاء. اقترب إلى أقل من 200 مترًا».
  Future<void> arrived(int rideId, {double? lat, double? lng}) =>
      _client.post<dynamic>('/driver/rides/$rideId/arrived/', body: {
        'lat': ?lat,
        'lng': ?lng,
      });

  /// تراجعٌ بعد القبول وقبل البدء. السبب إلزاميّ، والطلب يعود إلى البحث
  /// للزبون. تكراره يوقف السائق عن العروض مؤقّتًا (سياسة الإلغاء).
  ///
  /// إلّا [DriverCancelReason.customerNoShow] بعد الوصول والانتظار: لا يُحسب
  /// عليه، والرحلة العائدة تحمل `driverCompensation` إن عُوِّض.
  Future<Trip> cancelTrip(
    int rideId, {
    required String reason,
    DriverCancelReason? reasonCode,
  }) async {
    final json = await _client.post<Json>(
      '/driver/rides/$rideId/cancel/',
      body: {'reason': reason, 'reason_code': ?reasonCode?.code},
    );
    return Trip.fromJson(json);
  }

  /// يردّ `trip.not_arrived` إن لم يسبقه `arrived`.
  Future<void> start(int rideId) =>
      _client.post<dynamic>('/driver/rides/$rideId/start/');

  /// يردّ `trip.not_started` إن لم يسبقه `start`.
  ///
  /// والموقع من النبضة لا من الجسم — كما في `arrived`. ونطاق الإنزال
  /// أوسع عمدًا (300 مترًا مقابل 200) لأنّ الوجهة قد تتغيّر قليلًا بطلب
  /// الراكب.
  Future<Json> complete(int rideId,
          {required double lat, required double lng}) async =>
      asJson(await _client.post<dynamic>(
        '/driver/rides/$rideId/complete/',
        body: {'lat': lat, 'lng': lng},
      ));

  Future<DriverBalance> balance() async =>
      DriverBalance.fromList(await _client.get<dynamic>('/me/driver-balance/'));

  /// برامج الحوافز وتقدّم السائق فيها.
  Future<List<IncentiveProgress>> incentives() async {
    final body = await _client.get<dynamic>('/me/incentives/');
    return [
      for (final row in (body as List? ?? const []))
        if (row is Map) IncentiveProgress.fromJson(row.cast<String, dynamic>()),
    ];
  }
}
