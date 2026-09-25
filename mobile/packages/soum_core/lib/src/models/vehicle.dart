import 'package:equatable/equatable.dart';

import 'json.dart';

class Vehicle extends Equatable {
  const Vehicle({
    required this.id,
    required this.type,
    required this.make,
    required this.model,
    required this.year,
    required this.color,
    required this.plateNumber,
    required this.seats,
    required this.active,
  });

  final int id;

  /// رمز الفئة — `sedan` وأمثالها. صفٌّ في الخادم لا عضو في تعداد:
  /// المشغّل يضيف «تكتك» أو «ميكروباص» بصفّ واحد، ولا يجوز للتطبيق أن
  /// يرفض رمزًا لم يعرفه وقت البناء.
  final String type;

  final String make;
  final String model;
  final int year;
  final String color;
  final String plateNumber;
  final int seats;
  final bool active;

  String get label => '$make $model';

  factory Vehicle.fromJson(Json json) => Vehicle(
        id: readInt(json, 'id'),
        type: readString(json, 'type'),
        make: readString(json, 'make'),
        model: readString(json, 'model'),
        year: readInt(json, 'year'),
        color: readString(json, 'color'),
        plateNumber: readString(json, 'plate_number'),
        seats: readInt(json, 'seats', fallback: 4),
        active: readBool(json, 'active'),
      );

  @override
  List<Object?> get props => [id, type, make, model, plateNumber, active];
}

/// مركبة العرض — كائن مصغَّر داخل `RideOffer`.
///
/// `plate_number` موجود هنا لأنّ هذا العرض يخصّ رحلة الزبون نفسه؛ خريطة
/// السوق العامّة لا تحمله (§9.1).
class OfferVehicle extends Equatable {
  const OfferVehicle({
    required this.type,
    required this.make,
    required this.model,
    required this.color,
    required this.plateNumber,
  });

  final String type;
  final String make;
  final String model;
  final String color;
  final String plateNumber;

  String get label => '$make $model';

  static OfferVehicle? fromJson(Json? json) {
    if (json == null) return null;
    return OfferVehicle(
      type: readString(json, 'type'),
      make: readString(json, 'make'),
      model: readString(json, 'model'),
      color: readString(json, 'color'),
      plateNumber: readString(json, 'plate_number'),
    );
  }

  @override
  List<Object?> get props => [type, make, model, color, plateNumber];
}
