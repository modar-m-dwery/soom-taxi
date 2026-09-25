import 'package:equatable/equatable.dart';

import 'geo.dart';
import 'json.dart';
import 'money.dart';

/// سيارة على الخريطة الحيّة.
///
/// ما فيها وما ليس فيها كلاهما مقصود (§9.1 و§5 في وثيقة المنتج):
/// إحداثيات مقرَّبة إلى ~110 أمتار، وتقييم ونوع ومقاعد — ولا رقم هاتف
/// ولا رقم لوحة ولا إحداثيات دقيقة قبل القبول. إحداثيةٌ دقيقة لسيارة
/// متوقّفة هي عنوان بيت سائقها.
class NearbyVehicle extends Equatable {
  const NearbyVehicle({
    required this.driverId,
    required this.driverName,
    required this.rating,
    required this.vehicleType,
    required this.vehicleMake,
    required this.vehicleModel,
    required this.vehicleColor,
    required this.seats,
    required this.availableSeats,
    required this.currentOccupancy,
    required this.position,
    required this.approximateDistanceM,
    required this.etaMinutes,
    required this.quotedFare,
    required this.isInvited,
    this.heading,
    this.isSharing = false,
    this.onboardPassengers,
    this.compatibilityScore,
    this.routeBearing,
    this.extraDetourM,
  });

  final int driverId;
  final String driverName;
  final double? rating;
  final String vehicleType;
  final String vehicleMake;
  final String vehicleModel;
  final String vehicleColor;
  final int seats;
  final int availableSeats;
  final int currentOccupancy;
  final GeoPoint position;
  final int approximateDistanceM;
  final int etaMinutes;
  final Money quotedFare;

  /// دعوةٌ قائمة لهذا السائق من هذا الطلب — تُستعمل لتعطيل زرّ الدعوة
  /// بدل أن يُرسل نداء يردّه الخادم بـ`invitation.parallel_limit`.
  final bool isInvited;

  final String? heading;

  /// سيارة على رحلة مشتركة وفيها مقعد فارغ.
  final bool isSharing;
  final int? onboardPassengers;
  final int? compatibilityScore;
  final double? routeBearing;
  final int? extraDetourM;

  String get vehicleLabel => '$vehicleMake $vehicleModel';

  factory NearbyVehicle.fromJson(Json json) => NearbyVehicle(
        driverId: readInt(json, 'driver_id'),
        driverName: readString(json, 'driver_name'),
        rating: readDoubleOrNull(json, 'rating'),
        vehicleType: readString(json, 'vehicle_type'),
        vehicleMake: readString(json, 'vehicle_make'),
        vehicleModel: readString(json, 'vehicle_model'),
        vehicleColor: readString(json, 'vehicle_color'),
        seats: readInt(json, 'seats', fallback: 4),
        availableSeats: readInt(json, 'available_seats'),
        currentOccupancy: readInt(json, 'current_occupancy'),
        position: GeoPoint(readDouble(json, 'lat'), readDouble(json, 'lng')),
        approximateDistanceM: readInt(json, 'approximate_distance_m'),
        etaMinutes: readInt(json, 'eta_minutes'),
        quotedFare: readMoney(json, 'quoted_fare',
            currency: readString(json, 'currency',
                fallback: Money.defaultCurrency)),
        isInvited: readBool(json, 'is_invited'),
        heading: readStringOrNull(json, 'heading'),
        isSharing: readBool(json, 'is_sharing'),
        onboardPassengers: readIntOrNull(json, 'onboard_passengers'),
        compatibilityScore: readIntOrNull(json, 'compatibility_score'),
        routeBearing: readDoubleOrNull(json, 'route_bearing'),
        extraDetourM: readIntOrNull(json, 'extra_detour_m'),
      );

  @override
  List<Object?> get props =>
      [driverId, position, availableSeats, isInvited, etaMinutes];
}
