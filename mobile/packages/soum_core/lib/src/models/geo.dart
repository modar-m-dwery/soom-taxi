import 'package:equatable/equatable.dart';

import 'json.dart';

/// نقطة جغرافية.
///
/// الترتيب في هذا المشروع مصدر خطأ متكرّر: PostGIS و GeoJSON يكتبان
/// `(lng, lat)`، وواجهات الخرائط تكتب `(lat, lng)`. الخادم يرسل الحقلين
/// مسمّيين دائمًا، فنبني منهما بالاسم ولا نقرأ مصفوفة بالموضع إلّا في
/// `route_geometry` — وهناك نصرّح بالترتيب.
class GeoPoint extends Equatable {
  const GeoPoint(this.lat, this.lng);

  final double lat;
  final double lng;

  static GeoPoint? fromJson(Json? json) {
    if (json == null) return null;
    final lat = readDoubleOrNull(json, 'lat');
    final lng = readDoubleOrNull(json, 'lng');
    if (lat == null || lng == null) return null;
    return GeoPoint(lat, lng);
  }

  /// من حقلين مسطّحين على كائن أكبر، مثل `pickup_lat` و`pickup_lng`.
  static GeoPoint? fromFields(Json json, String prefix) {
    final lat = readDoubleOrNull(json, '${prefix}_lat');
    final lng = readDoubleOrNull(json, '${prefix}_lng');
    if (lat == null || lng == null) return null;
    return GeoPoint(lat, lng);
  }

  Json toJson() => {'lat': lat, 'lng': lng};

  @override
  List<Object?> get props => [lat, lng];

  @override
  String toString() => '($lat, $lng)';
}

/// هندسة المسار كما يرسلها OSRM: ‏GeoJSON LineString بترتيب `[lng, lat]`.
///
/// تُقلب هنا مرّة واحدة إلى `GeoPoint`، فلا تتكرّر مخاطرة القلب في كلّ
/// شاشة ترسم خطًّا. و`null` قيمة صحيحة: ‏`route_source: estimated` يعني
/// أنّه لا مسار — ورسمُ خطّ مستقيم بدله كذبٌ بصريّ.
class RouteGeometry extends Equatable {
  const RouteGeometry(this.points);

  final List<GeoPoint> points;

  bool get isEmpty => points.isEmpty;

  static RouteGeometry? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final coordinates = raw['coordinates'];
    if (coordinates is! List || coordinates.isEmpty) return null;

    final points = <GeoPoint>[];
    for (final pair in coordinates) {
      if (pair is List && pair.length >= 2) {
        final lng = (pair[0] as num?)?.toDouble();
        final lat = (pair[1] as num?)?.toDouble();
        if (lat != null && lng != null) points.add(GeoPoint(lat, lng));
      }
    }
    return points.isEmpty ? null : RouteGeometry(points);
  }

  @override
  List<Object?> get props => [points];
}
