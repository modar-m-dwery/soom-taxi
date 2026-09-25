import 'package:equatable/equatable.dart';

import 'enums.dart';
import 'json.dart';
import 'money.dart';

/// دعوة سائق بعينه — المسار الأقصر من المزاد والأقسى في المهل.
class RideInvitation extends Equatable {
  const RideInvitation({
    required this.id,
    required this.rideId,
    required this.driverId,
    required this.driverName,
    required this.driverRating,
    required this.vehicleType,
    required this.vehicleMake,
    required this.vehicleModel,
    required this.vehicleColor,
    required this.status,
    required this.ttlSeconds,
    required this.serverSecondsRemaining,
    required this.sentAt,
    required this.expiresAt,
    required this.quotedFare,
    this.respondedAt,
    this.approximateDistanceM,
    this.etaMinutes,
    this.availableSeats,
    this.counterFare,
    this.rejectReason = '',
  });

  final int id;
  final int rideId;
  final int driverId;
  final String driverName;
  final double? driverRating;
  final String vehicleType;
  final String vehicleMake;
  final String vehicleModel;
  final String vehicleColor;
  final InvitationStatus status;

  /// المهلة المرسَلة — واحدة من `invitation_ttl_options` حصرًا.
  final int ttlSeconds;

  /// ما يقوله الخادم وقت القراءة. نحسب العدّاد من `expiresAt` لأنّه
  /// يستمرّ بين النداءات، ونستعمل هذا للمطابقة عند أوّل رسم.
  final int serverSecondsRemaining;

  final DateTime sentAt;
  final DateTime expiresAt;
  final Money quotedFare;
  final DateTime? respondedAt;

  /// ~110 مترًا من الدقّة — تكفي لرسم نقطة ولا تكفي لتتبّع إنسان.
  final int? approximateDistanceM;

  final int? etaMinutes;
  final int? availableSeats;
  final Money? counterFare;
  final String rejectReason;

  bool get isPending => status == InvitationStatus.pending;

  int secondsRemaining([DateTime? now]) {
    if (!isPending) return 0;
    final left = expiresAt.difference(now ?? DateTime.now()).inSeconds;
    return left < 0 ? 0 : left;
  }

  factory RideInvitation.fromJson(Json json) => RideInvitation(
        // الـREST يقول `id` وحدث المقبس `invitation.created` يقول
        // `invitation_id`. بلا البديل كان المعرّف صفرًا، و«اقبل» يضرب
        // `/invitations/0/accept/` فيردّ 404 والدعوة تنقضي (العيب #34).
        id: readInt(json, 'id', fallback: readInt(json, 'invitation_id')),
        rideId: readInt(json, 'ride'),
        driverId: readInt(json, 'driver'),
        driverName: readString(json, 'driver_name'),
        driverRating: readDoubleOrNull(json, 'driver_rating'),
        vehicleType: readString(json, 'vehicle_type'),
        vehicleMake: readString(json, 'vehicle_make'),
        vehicleModel: readString(json, 'vehicle_model'),
        vehicleColor: readString(json, 'vehicle_color'),
        status: InvitationStatus.from(readStringOrNull(json, 'status')),
        ttlSeconds: readInt(json, 'ttl_seconds'),
        serverSecondsRemaining: readInt(json, 'seconds_remaining'),
        sentAt: readDate(json, 'sent_at'),
        expiresAt: readDate(json, 'expires_at'),
        quotedFare: readMoney(json, 'quoted_fare'),
        respondedAt: readDateOrNull(json, 'responded_at'),
        approximateDistanceM: readIntOrNull(json, 'approximate_distance_m'),
        etaMinutes: readIntOrNull(json, 'eta_minutes'),
        availableSeats: readIntOrNull(json, 'available_seats'),
        counterFare: readMoneyOrNull(json, 'counter_fare'),
        rejectReason: readString(json, 'reject_reason'),
      );

  @override
  List<Object?> get props => [id, status, expiresAt, quotedFare];
}
