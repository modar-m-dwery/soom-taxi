/// المشاركة والرحلات المنشورة.
///
/// ثلاثة مسارات مختلفة يخلطها من يقرأ الوثيقة سريعًا:
///
/// **المشاركة الفورية** — راكبٌ ينضمّ إلى رحلة **قائمة الآن**. الطلب
/// يُنشأ بنمط `shared`، ثمّ `/customer/rides/{id}/shared-offers/` يبحث عن
/// مجموعات فيها مقعد، والقبول يضمّه إليها.
///
/// **المشاركة المجدولة** — رحلة في المستقبل بنافذة ستّين دقيقة وأنصاف
/// أقطار خاصّة للانطلاق والوجهة. المرشَّحون من
/// `/customer/rides/{id}/scheduled-shared-trips/`.
///
/// **الرحلات المنشورة** — سفريّة أو سرفيس أو ترفيهية ينشرها السائق
/// بمقاعد وسعر، والزبون يحجز مقعدًا من كتالوج عامّ. لا مطابقة هنا: العرض
/// موجود قبل الطلب.
///
/// والفرق عمليّ لا تصنيفيّ: الأوّل يتقاسم أجرة رحلة قائمة، والثالث يبيع
/// مقعدًا بسعر معلن.
library;

import '../models/enums.dart';
import '../models/geo.dart';
import '../models/json.dart';
import '../models/money.dart';
import '../network/api_client.dart';

/// عرض انضمام إلى رحلة مشتركة قائمة.
class SharedJoinOffer {
  const SharedJoinOffer({
    required this.id,
    required this.compatibilityScore,
    required this.expiresAt,
    required this.vehicleType,
    required this.vehicleLabel,
    required this.seatsAvailable,
    required this.fareEstimate,
    required this.etaMinutes,
    this.driverRating,
    this.genderSummary,
  });

  final int id;

  /// درجة توافق المسار من 100 — كم يضيف هذا الراكب على طريق الآخرين.
  final String compatibilityScore;

  final DateTime expiresAt;
  final String vehicleType;
  final String vehicleLabel;
  final int? seatsAvailable;
  final Money fareEstimate;
  final int? etaMinutes;
  final String? driverRating;

  /// توزيع جنس الركّاب على المتن — `null` حين يمنعه المشغّل.
  ///
  /// هذا حقلٌ حسّاس بطبيعته: يُعرض لأنّه ما يجعل راكبةً تقبل المشاركة أو
  /// ترفضها، ويُخفى كاملًا حين يقرّر المشغّل ذلك. والقرار من الخادم لا
  /// من التطبيق.
  final Map<String, int>? genderSummary;

  factory SharedJoinOffer.fromJson(Json json) => SharedJoinOffer(
        id: readInt(json, 'id'),
        compatibilityScore: readString(json, 'compatibility_score'),
        expiresAt: readDate(json, 'expires_at'),
        vehicleType: readString(json, 'vehicle_type'),
        vehicleLabel: readString(json, 'vehicle_make_model'),
        seatsAvailable: readIntOrNull(json, 'seats_available'),
        fareEstimate: readMoney(json, 'fare_estimate'),
        etaMinutes: readIntOrNull(json, 'eta_minutes'),
        driverRating: readStringOrNull(json, 'driver_rating'),
        genderSummary: () {
          final raw = asJsonOrNull(json['passengers_gender_summary']);
          if (raw == null) return null;
          return {
            for (final entry in raw.entries)
              entry.key: int.tryParse('${entry.value}') ?? 0,
          };
        }(),
      );
}

/// رحلة مشتركة مجدولة — مرشَّحة للانضمام.
class ScheduledSharedTrip {
  const ScheduledSharedTrip({
    required this.id,
    required this.tripCategory,
    required this.scheduledAt,
    required this.capacity,
    required this.remainingCapacity,
    required this.driverName,
    required this.vehicleLabel,
    required this.status,
    this.title,
    this.description,
    this.originCity,
    this.destinationCity,
    this.pricePerSeat,
    this.pickup,
    this.destination,
    this.driverRating,
    this.features = const [],
  });

  final int id;
  final TripCategory tripCategory;
  final DateTime scheduledAt;
  final int capacity;
  final int remainingCapacity;
  final String driverName;
  final String vehicleLabel;
  final String status;

  final String? title;
  final String? description;
  final String? originCity;
  final String? destinationCity;
  final Money? pricePerSeat;

  /// مقرَّبتان إلى ~110 أمتار — الكتالوج عامّ، وإحداثيةٌ دقيقة مربوطة
  /// باسم سائق وموعد هي عنوانٌ وموعد.
  final GeoPoint? pickup;
  final GeoPoint? destination;

  final String? driverRating;
  final List<String> features;

  bool get hasRoom => remainingCapacity > 0;

  factory ScheduledSharedTrip.fromJson(Json json) => ScheduledSharedTrip(
        id: readInt(json, 'id'),
        tripCategory: TripCategory.from(readStringOrNull(json, 'trip_category')),
        scheduledAt: readDate(json, 'scheduled_at'),
        capacity: readInt(json, 'capacity'),
        remainingCapacity: readInt(json, 'remaining_capacity'),
        driverName: readString(json, 'driver_name'),
        vehicleLabel: [
          readString(json, 'vehicle_make'),
          readString(json, 'vehicle_model'),
        ].where((part) => part.isNotEmpty).join(' '),
        status: readString(json, 'status'),
        title: readStringOrNull(json, 'title'),
        description: readStringOrNull(json, 'description'),
        originCity: readStringOrNull(json, 'origin_city'),
        destinationCity: readStringOrNull(json, 'destination_city'),
        pricePerSeat: readMoneyOrNull(json, 'price_per_seat'),
        pickup: GeoPoint.fromJson(asJsonOrNull(json['pickup'])),
        destination: GeoPoint.fromJson(asJsonOrNull(json['destination'])),
        driverRating: readStringOrNull(json, 'driver_rating'),
        features: readStringList(json, 'features'),
      );
}

class SharingApi {
  SharingApi(this._client);

  final ApiClient _client;

  // -----------------------------------------------------------------
  // المشاركة الفورية
  // -----------------------------------------------------------------

  /// مجموعات مشتركة قائمة فيها مقعد لهذا الطلب.
  Future<List<SharedJoinOffer>> sharedOffers(int rideId) async {
    final body =
        await _client.get<dynamic>('/customer/rides/$rideId/shared-offers/');
    return readResults(body).map(SharedJoinOffer.fromJson).toList(growable: false);
  }

  /// قبول الانضمام. قد يُرفض إن شغل راكب آخر المقعد بين العرض والقبول —
  /// نفس سباق المزاد، وبالمعالجة نفسها: رسالة لطيفة وقائمة محدَّثة.
  Future<Json> acceptSharedOffer(int joinRequestId) async =>
      asJson(await _client.post<dynamic>(
        '/customer/shared-offers/$joinRequestId/accept/',
      ));

  // -----------------------------------------------------------------
  // المشاركة المجدولة
  // -----------------------------------------------------------------

  /// رحلات مجدولة متوافقة مع هذا الطلب.
  ///
  /// التوافق يحسبه الخادم بنافذة `shared_scheduled_time_window_minutes`
  /// وأنصاف أقطار الانطلاق والوجهة. رحلةٌ خارجها لا تظهر أصلًا — فلا
  /// معنى لترشيح محلّيّ فوقه.
  Future<List<ScheduledSharedTrip>> scheduledSharedTrips(int rideId) async {
    final body = await _client
        .get<dynamic>('/customer/rides/$rideId/scheduled-shared-trips/');
    return readResults(body)
        .map(ScheduledSharedTrip.fromJson)
        .toList(growable: false);
  }

  Future<Json> joinScheduledSharedTrip({
    required int rideId,
    required int tripId,
  }) async =>
      asJson(await _client.post<dynamic>(
        '/customer/rides/$rideId/scheduled-shared-trips/$tripId/join/',
      ));

  // -----------------------------------------------------------------
  // الرحلات المنشورة
  // -----------------------------------------------------------------

  /// الكتالوج العامّ — سفريات وسرفيس ورحلات ترفيهية.
  Future<List<ScheduledSharedTrip>> publishedTrips({
    String? category,
    String? originCity,
    String? destinationCity,
  }) async {
    final body = await _client.get<dynamic>('/trips/', query: {
      'trip_category': ?category,
      'origin_city': ?originCity,
      'destination_city': ?destinationCity,
    });
    return readResults(body)
        .map(ScheduledSharedTrip.fromJson)
        .toList(growable: false);
  }

  Future<Json> bookPublishedTrip({
    required int tripId,
    int passengerCount = 1,
  }) async =>
      asJson(await _client.post<dynamic>(
        '/trips/$tripId/book/',
        body: {'passenger_count': passengerCount},
      ));

  /// نشر رحلة — من تطبيق السائق.
  Future<Json> publishTrip({
    required int vehicleId,
    required String tripCategory,
    required DateTime scheduledAt,
    required int capacity,
    required GeoPoint pickup,
    required GeoPoint destination,
    String? originCity,
    String? destinationCity,
    Money? pricePerSeat,
    String? title,
    String? description,
    List<String> features = const [],
  }) async =>
      asJson(await _client.post<dynamic>('/driver/trips/publish/', body: {
        'vehicle_id': vehicleId,
        'trip_category': tripCategory,
        'scheduled_at': scheduledAt.toUtc().toIso8601String(),
        'capacity': capacity,
        'pickup_lat': pickup.lat,
        'pickup_lng': pickup.lng,
        'destination_lat': destination.lat,
        'destination_lng': destination.lng,
        'origin_city': ?originCity,
        'destination_city': ?destinationCity,
        'price_per_seat': ?pricePerSeat?.toApi(),
        'title': ?title,
        'description': ?description,
        if (features.isNotEmpty) 'features': features,
      }));
}
