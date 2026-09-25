import 'package:equatable/equatable.dart';

import 'enums.dart';
import 'json.dart';
import 'money.dart';
import 'vehicle.dart';

/// عرض سائق في المزاد.
class RideOffer extends Equatable {
  const RideOffer({
    required this.id,
    required this.rideId,
    required this.driverId,
    required this.driverName,
    required this.driverRating,
    required this.grossFare,
    required this.etaMinutes,
    required this.status,
    required this.expiresAt,
    this.vehicle,
    this.acceptedAt,
  });

  final int id;
  final int rideId;
  final int driverId;
  final String driverName;
  final double? driverRating;
  final Money grossFare;
  final int etaMinutes;
  final OfferStatus status;

  /// العدّاد على بطاقة العرض يُبنى على هذا لا على `offer_ttl_seconds`:
  /// العرض قد يكون وصل متأخّرًا، فمهلته المتبقّية أقلّ من مهلته الكاملة.
  final DateTime expiresAt;

  final OfferVehicle? vehicle;
  final DateTime? acceptedAt;

  int secondsRemaining([DateTime? now]) {
    if (!status.isLive) return 0;
    final left = expiresAt.difference(now ?? DateTime.now()).inSeconds;
    return left < 0 ? 0 : left;
  }

  factory RideOffer.fromJson(Json json) => RideOffer(
        id: readInt(json, 'id'),
        rideId: readInt(json, 'ride'),
        driverId: readInt(json, 'driver_id'),
        driverName: readString(json, 'driver_name'),
        driverRating: readDoubleOrNull(json, 'driver_rating'),
        grossFare: readMoney(json, 'gross_fare'),
        etaMinutes: readInt(json, 'eta_minutes'),
        status: OfferStatus.from(readStringOrNull(json, 'status')),
        expiresAt: readDate(json, 'expires_at'),
        vehicle: OfferVehicle.fromJson(asJsonOrNull(json['vehicle'])),
        acceptedAt: readDateOrNull(json, 'accepted_at'),
      );

  @override
  List<Object?> get props => [id, status, grossFare, etaMinutes, expiresAt];
}
