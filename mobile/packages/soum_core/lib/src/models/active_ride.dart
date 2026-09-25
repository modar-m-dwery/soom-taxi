import 'package:equatable/equatable.dart';

import 'enums.dart';
import 'json.dart';
import 'payment.dart';
import 'ride.dart';
import 'trip.dart';

/// المرحلة التي يفتح عليها التطبيق.
///
/// §2.2 في دليل التكامل يسمّيها «أهمّ نقطة في الوثيقة كلّها». والسبب أنّ
/// البديل — إعادة بناء الحالة من سجلّ الرحلات — يخطئ بطرق لا تُكتشف:
/// طلبٌ انقضت مهلته في Celery، أو إدارةٌ ألغت رحلة، أو سائقٌ انقطع. نداءٌ
/// واحد يعرف ذلك كلّه، وحسابٌ محلّيّ لا يعرفه.
///
/// القيم ثابتة من جهة الخادم ولا تتغيّر بعد الإطلاق — تغييرها يكسر شاشةً
/// عند مستخدم لم يُحدّث تطبيقه.
enum ResumeStage {
  idle('idle'),
  searching('searching'),
  choosingOffer('choosing_offer'),
  driverAssigned('driver_assigned'),
  driverArriving('driver_arriving'),
  driverArrived('driver_arrived'),
  inProgress('in_progress'),

  /// رحلةٌ انتهت ولم تُدفع. §12.3: هذه تفتح شاشة الدفع لا الرئيسية.
  awaitingPayment('awaiting_payment'),

  unknown('unknown');

  const ResumeStage(this.code);
  final String code;

  static ResumeStage from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => ResumeStage.unknown,
      );

  bool get isIdle => this == ResumeStage.idle;

  /// المراحل التي تُعرض على شاشة تتبّع.
  bool get isOnTrip => const {
        ResumeStage.driverAssigned,
        ResumeStage.driverArriving,
        ResumeStage.driverArrived,
        ResumeStage.inProgress,
      }.contains(this);
}

/// أسماء الغرف كما يبنيها الخادم.
///
/// تُقرأ ولا تُبنى في التطبيق: أيّ تغيير في مسارات البثّ غدًا كان سيتطلّب
/// إصدارًا جديدًا على المتجر لو كانت مبنيّة هنا.
class RealtimeRooms extends Equatable {
  const RealtimeRooms({this.rideRoom, this.driverRoom});

  final String? rideRoom;
  final String? driverRoom;

  factory RealtimeRooms.fromJson(Json json) => RealtimeRooms(
        rideRoom: readStringOrNull(json, 'ride_room'),
        driverRoom: readStringOrNull(json, 'driver_room'),
      );

  @override
  List<Object?> get props => [rideRoom, driverRoom];
}

class ActiveRideSnapshot extends Equatable {
  const ActiveRideSnapshot({
    required this.hasActiveRide,
    required this.role,
    required this.stage,
    required this.rooms,
    this.ride,
    this.trip,
    this.pendingPayment,
    this.otherTrips = const [],
  });

  final bool hasActiveRide;
  final UserRole role;
  final ResumeStage stage;
  final RealtimeRooms rooms;
  final RideRequest? ride;
  final Trip? trip;

  /// غير فارغ = رحلةٌ انتهت ولم تُدفع.
  final Payment? pendingPayment;

  bool get needsPayment => pendingPayment != null;

  /// السائق في رحلة مشتركة: رحلات الركّاب الآخرين، كلٌّ بتسلسله وأجرته.
  final List<DriverTripEntry> otherTrips;

  /// كلّ الرحلات النشطة للسائق — الرئيسيّة أوّلًا.
  List<DriverTripEntry> get allTrips => [
        if (ride != null)
          DriverTripEntry(ride: ride!, trip: trip, rideRoom: rooms.rideRoom),
        ...otherTrips,
      ];

  factory ActiveRideSnapshot.fromJson(Json json) {
    final ride = asJsonOrNull(json['ride']);
    final trip = asJsonOrNull(json['trip']);
    final payment = asJsonOrNull(json['pending_payment']);

    return ActiveRideSnapshot(
      hasActiveRide: readBool(json, 'has_active_ride'),
      role: UserRole.from(readStringOrNull(json, 'role')),
      stage: ResumeStage.from(readStringOrNull(json, 'stage')),
      rooms: RealtimeRooms.fromJson(asJson(json['realtime'])),
      ride: ride == null ? null : RideRequest.fromJson(ride),
      trip: trip == null ? null : Trip.fromJson(trip),
      pendingPayment: payment == null ? null : Payment.fromJson(payment),
      otherTrips: [
        for (final entry in (json['other_trips'] as List?) ?? const [])
          if (entry is Map && entry['ride'] is Map)
            DriverTripEntry(
              ride: RideRequest.fromJson((entry['ride'] as Map).cast<String, dynamic>()),
              trip: entry['trip'] is Map
                  ? Trip.fromJson((entry['trip'] as Map).cast<String, dynamic>())
                  : null,
              rideRoom: entry['ride_room'] is String ? entry['ride_room'] as String : null,
            ),
      ],
    );
  }

  @override
  List<Object?> get props =>
      [hasActiveRide, stage, ride, trip, pendingPayment, otherTrips];
}

/// رحلة راكب واحد عند السائق.
class DriverTripEntry extends Equatable {
  const DriverTripEntry({required this.ride, this.trip, this.rideRoom});

  final RideRequest ride;
  final Trip? trip;

  /// مسار غرفة الرحلة كما بناه الخادم.
  final String? rideRoom;

  @override
  List<Object?> get props => [ride, trip];
}
