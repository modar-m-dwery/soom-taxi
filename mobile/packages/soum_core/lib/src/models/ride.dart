import 'package:equatable/equatable.dart';

import 'enums.dart';
import 'geo.dart';
import 'json.dart';
import 'money.dart';

/// تفصيل الأجرة كما يبنيه الخادم.
///
/// §4.1 في وثيقة المنتج: كلّ مكوّن يعود منفصلًا، والزبون يرى «لماذا هذا
/// السعر» لا رقمًا نهائيًّا فقط. هذا ليس ترفًا في الواجهة — بل هو ما يمنع
/// نصف الشكاوى قبل وقوعها، فالشكوى تبدأ غالبًا بـ«لماذا دفعت هذا؟».
class FareBreakdown extends Equatable {
  const FareBreakdown({
    required this.baseFare,
    required this.distanceFare,
    required this.timeFare,
    required this.grossFare,
    required this.platformFee,
    required this.customerTotal,
    required this.driverNet,
    required this.surgeMultiplier,
    required this.currency,
    this.fareFloor,
    this.fareCap,
    this.pricingPolicy = '',
  });

  final Money baseFare;
  final Money distanceFare;
  final Money timeFare;
  final Money grossFare;

  /// صفر في النسخة الحالية — عمولة المنصّة معطَّلة بقيمة صفر. البنية
  /// تدعمها كاملةً، وتفعيلها تغييرُ رقم في لوحة الإدارة.
  final Money platformFee;

  /// ما يدفعه الزبون.
  final Money customerTotal;

  /// ما يقبضه السائق.
  final Money driverNet;

  final String surgeMultiplier;
  final String currency;

  /// ممرّ التفاوض: عرضٌ خارجه يُرفض من الخادم. تُعرض حدوده للسائق قبل
  /// أن يرسل سعرًا مرفوضًا.
  final Money? fareFloor;
  final Money? fareCap;

  final String pricingPolicy;

  bool get hasSurge => surgeMultiplier.isNotEmpty &&
      (double.tryParse(surgeMultiplier) ?? 1) > 1;

  factory FareBreakdown.fromJson(Json json) {
    final currency = readString(json, 'currency', fallback: Money.defaultCurrency);
    return FareBreakdown(
      baseFare: readMoney(json, 'base_fare', currency: currency),
      distanceFare: readMoney(json, 'distance_fare', currency: currency),
      timeFare: readMoney(json, 'time_fare', currency: currency),
      grossFare: readMoney(json, 'gross_fare', currency: currency),
      platformFee: readMoney(json, 'platform_fee', currency: currency),
      customerTotal: readMoney(json, 'customer_total', currency: currency),
      driverNet: readMoney(json, 'driver_net', currency: currency),
      surgeMultiplier: readString(json, 'surge_multiplier', fallback: '1.00'),
      currency: currency,
      fareFloor: readMoneyOrNull(json, 'fare_floor', currency: currency),
      fareCap: readMoneyOrNull(json, 'fare_cap', currency: currency),
      pricingPolicy: readString(json, 'pricing_policy'),
    );
  }

  @override
  List<Object?> get props =>
      [baseFare, distanceFare, timeFare, grossFare, platformFee, customerTotal];
}

class RideRequest extends Equatable {
  const RideRequest({
    required this.id,
    required this.status,
    required this.mode,
    required this.tripCategory,
    required this.passengerCount,
    required this.fare,
    required this.routeSource,
    this.pickup,
    this.destination,
    this.requestedVehicleType,
    this.originCity,
    this.destinationCity,
    this.publishedTripId,
    this.scheduledAt,
    this.expiresAt,
    this.estimatedDistanceKm,
    this.estimatedDurationMinutes,
    this.routeDistanceKm,
    this.routeDurationMinutes,
    this.routeGeometry,
    this.searchRadiusKm,
    this.autoDispatch = false,
    this.customerLateCancels = 0,
    required this.createdAt,
  });

  final int id;
  final RideStatus status;
  final RideMode mode;
  final TripCategory tripCategory;
  final int passengerCount;
  final FareBreakdown fare;

  /// §3.2: يُعرض للمستخدم — «سعر المسار» أو «سعر تقريبي».
  final RouteSource routeSource;

  final GeoPoint? pickup;
  final GeoPoint? destination;
  final String? requestedVehicleType;
  final String? originCity;
  final String? destinationCity;
  final int? publishedTripId;
  final DateTime? scheduledAt;

  /// §3.2: «ابنِ العدّاد على هذا» — لا على مدّة محسوبة محلّيًّا.
  final DateTime? expiresAt;

  final String? estimatedDistanceKm;
  final int? estimatedDurationMinutes;
  final String? routeDistanceKm;
  final int? routeDurationMinutes;

  /// فارغ حين يكون `routeSource` تقديرًا — ولا يُرسم خطّ عندها.
  final RouteGeometry? routeGeometry;

  final DateTime createdAt;

  /// النطاق الذي اختاره الزبون، أو null = نطاق المنطقة.
  final double? searchRadiusKm;

  /// «الأقرب»: الخادم يدعو السائقين بالتتابع. يصير false حين يُنهَك.
  final bool autoDispatch;

  /// للسائق: مخالفات الإلغاء المتأخّر على صاحب الطلب هذا الأسبوع.
  final int customerLateCancels;

  bool get isScheduled => scheduledAt != null;

  /// الثواني المتبقّية على مهلة البحث، أو null حين لا مهلة.
  int? secondsUntilExpiry([DateTime? now]) {
    final deadline = expiresAt;
    if (deadline == null) return null;
    final left = deadline.difference(now ?? DateTime.now()).inSeconds;
    return left < 0 ? 0 : left;
  }

  factory RideRequest.fromJson(Json json) => RideRequest(
        id: readInt(json, 'id'),
        status: RideStatus.from(readStringOrNull(json, 'status')),
        mode: RideMode.from(readStringOrNull(json, 'mode')),
        tripCategory: TripCategory.from(readStringOrNull(json, 'trip_category')),
        passengerCount: readInt(json, 'passenger_count', fallback: 1),
        fare: FareBreakdown.fromJson(json),
        routeSource: RouteSource.from(readStringOrNull(json, 'route_source')),
        pickup: GeoPoint.fromFields(json, 'pickup'),
        destination: GeoPoint.fromFields(json, 'destination'),
        requestedVehicleType: readStringOrNull(json, 'requested_vehicle_type'),
        originCity: readStringOrNull(json, 'origin_city'),
        destinationCity: readStringOrNull(json, 'destination_city'),
        publishedTripId: readIntOrNull(json, 'published_trip'),
        scheduledAt: readDateOrNull(json, 'scheduled_at'),
        expiresAt: readDateOrNull(json, 'expires_at'),
        estimatedDistanceKm: readStringOrNull(json, 'estimated_distance_km'),
        estimatedDurationMinutes: readIntOrNull(json, 'estimated_duration_minutes'),
        routeDistanceKm: readStringOrNull(json, 'route_distance_km'),
        routeDurationMinutes: readIntOrNull(json, 'route_duration_minutes'),
        routeGeometry: RouteGeometry.fromJson(json['route_geometry']),
        searchRadiusKm: readDoubleOrNull(json, 'search_radius_km'),
        autoDispatch: readBool(json, 'auto_dispatch'),
        customerLateCancels: readInt(json, 'customer_late_cancels', fallback: 0),
        createdAt: readDate(json, 'created_at'),
      );

  @override
  List<Object?> get props => [id, status, mode, expiresAt, fare, autoDispatch];
}
