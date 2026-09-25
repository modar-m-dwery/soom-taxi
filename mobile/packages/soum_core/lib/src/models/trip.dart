import 'package:equatable/equatable.dart';

import 'enums.dart';
import 'json.dart';
import 'money.dart';

class Trip extends Equatable {
  const Trip({
    required this.id,
    required this.rideId,
    required this.status,
    required this.driverId,
    required this.driverName,
    this.driverPhone,
    this.customerName = '',
    this.customerPhone,
    required this.driverRating,
    required this.vehicleType,
    required this.vehicleMake,
    required this.vehicleModel,
    required this.vehicleColor,
    required this.vehiclePlate,
    required this.finalFare,
    required this.currency,
    required this.pickupVerified,
    required this.dropoffVerified,
    required this.needsReview,
    required this.createdAt,
    this.arrivingAt,
    this.arrivedAt,
    this.startedAt,
    this.completedAt,
    this.cancelledAt,
    this.distanceM,
    this.durationS,
    this.gpsPointsCount = 0,
    this.reviewReason = '',
    this.cancelledBy = '',
    this.cancelReason = '',
  });

  final int id;
  final int rideId;
  final TripStatus status;
  final int driverId;
  final String driverName;
  final double? driverRating;

  /// أرقام الطرفين — يرسلها الخادم ما دامت الرحلة نشطة وحدها.
  final String? driverPhone;
  final String customerName;
  final String? customerPhone;

  /// بيانات المركبة كاملةً — بعد القبول، ورقم اللوحة يظهر هنا لأنّ
  /// الزبون صار طرفًا في هذه الرحلة.
  final String vehicleType;
  final String vehicleMake;
  final String vehicleModel;
  final String vehicleColor;
  final String vehiclePlate;

  final Money finalFare;
  final String currency;

  final bool pickupVerified;
  final bool dropoffVerified;

  /// إنهاءٌ بعيد عن الوجهة لا يُحجب بل يُعلَّم، فيظهر في لوحة المشغّل.
  /// الحجب يعاقب البريء، والقبول الصامت يكافئ المحتال.
  final bool needsReview;
  final String reviewReason;

  final DateTime createdAt;
  final DateTime? arrivingAt;
  final DateTime? arrivedAt;
  final DateTime? startedAt;
  final DateTime? completedAt;
  final DateTime? cancelledAt;

  final int? distanceM;
  final int? durationS;
  final int gpsPointsCount;

  final String cancelledBy;
  final String cancelReason;

  String get vehicleLabel => '$vehicleMake $vehicleModel';

  bool get isRunning => const {
        TripStatus.created,
        TripStatus.driverArriving,
        TripStatus.driverArrived,
        TripStatus.inProgress,
      }.contains(status);

  factory Trip.fromJson(Json json) {
    final currency = readString(json, 'currency', fallback: Money.defaultCurrency);
    return Trip(
      id: readInt(json, 'id'),
      rideId: readInt(json, 'ride'),
      status: TripStatus.from(readStringOrNull(json, 'status')),
      driverId: readInt(json, 'driver'),
      driverName: readString(json, 'driver_name'),
      driverPhone: readStringOrNull(json, 'driver_phone'),
      customerName: readString(json, 'customer_name'),
      customerPhone: readStringOrNull(json, 'customer_phone'),
      driverRating: readDoubleOrNull(json, 'driver_rating'),
      vehicleType: readString(json, 'vehicle_type'),
      vehicleMake: readString(json, 'vehicle_make'),
      vehicleModel: readString(json, 'vehicle_model'),
      vehicleColor: readString(json, 'vehicle_color'),
      vehiclePlate: readString(json, 'vehicle_plate'),
      finalFare: readMoney(json, 'final_fare', currency: currency),
      currency: currency,
      pickupVerified: readBool(json, 'pickup_verified'),
      dropoffVerified: readBool(json, 'dropoff_verified'),
      needsReview: readBool(json, 'needs_review'),
      reviewReason: readString(json, 'review_reason'),
      createdAt: readDate(json, 'created_at'),
      arrivingAt: readDateOrNull(json, 'arriving_at'),
      arrivedAt: readDateOrNull(json, 'arrived_at'),
      startedAt: readDateOrNull(json, 'started_at'),
      completedAt: readDateOrNull(json, 'completed_at'),
      cancelledAt: readDateOrNull(json, 'cancelled_at'),
      distanceM: readIntOrNull(json, 'distance_m'),
      durationS: readIntOrNull(json, 'duration_s'),
      gpsPointsCount: readInt(json, 'gps_points_count'),
      cancelledBy: readString(json, 'cancelled_by'),
      cancelReason: readString(json, 'cancel_reason'),
    );
  }

  @override
  List<Object?> get props => [id, status, finalFare, needsReview];
}
