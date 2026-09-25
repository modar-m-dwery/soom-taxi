/// «اشتراك الصباح» — صفٌّ واحد يولّد طلبًا مجدولًا كلّ يوم عمل.
///
/// الخادم هو من يُنشئ الطلب قبل الموعد بـ`leadMinutes`؛ التطبيق يكتب
/// الاشتراك ويقرأه فقط. `weekdays` بترقيم بايثون: 0=الاثنين … 6=الأحد،
/// والفارغ يعني أسبوع العمل السوريّ (الأحد–الخميس).
library;

import 'package:equatable/equatable.dart';

import 'geo.dart';
import 'json.dart';

/// الأحد–الخميس بترقيم الخادم.
const syrianWorkweek = <int>[6, 0, 1, 2, 3];

class RideSubscription extends Equatable {
  const RideSubscription({
    required this.id,
    required this.label,
    required this.pickup,
    required this.destination,
    required this.departureTime,
    required this.weekdays,
    required this.mode,
    required this.passengerCount,
    required this.requestedVehicleType,
    required this.leadMinutes,
    required this.isActive,
    required this.nextOccurrence,
    required this.createdAt,
  });

  final int id;
  final String label;
  final GeoPoint? pickup;
  final GeoPoint? destination;

  /// «07:30» كما يكتبها الخادم (توقيت دمشق).
  final String departureTime;
  final List<int> weekdays;
  final String mode;
  final int passengerCount;
  final String? requestedVehicleType;
  final int leadMinutes;
  final bool isActive;
  final DateTime? nextOccurrence;
  final DateTime createdAt;

  /// الأيام الفعليّة: الفارغ = أسبوع العمل.
  List<int> get effectiveWeekdays =>
      weekdays.isEmpty ? syrianWorkweek : weekdays;

  factory RideSubscription.fromJson(Json json) => RideSubscription(
        id: readInt(json, 'id'),
        label: readString(json, 'label'),
        pickup: GeoPoint.fromJson(asJsonOrNull(json['pickup'])),
        destination: GeoPoint.fromJson(asJsonOrNull(json['destination'])),
        departureTime: readString(json, 'departure_time'),
        weekdays: readIntList(json, 'weekdays'),
        mode: readString(json, 'mode', fallback: 'standard'),
        passengerCount: readInt(json, 'passenger_count', fallback: 1),
        requestedVehicleType: readStringOrNull(json, 'requested_vehicle_type'),
        leadMinutes: readInt(json, 'lead_minutes', fallback: 30),
        isActive: readBool(json, 'is_active', fallback: true),
        nextOccurrence: readDateOrNull(json, 'next_occurrence'),
        createdAt: readDate(json, 'created_at'),
      );

  @override
  List<Object?> get props => [id, isActive, nextOccurrence, departureTime];
}
