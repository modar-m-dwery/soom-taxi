/// حركة العلامات بين نبضات الموقع — حسابٌ نقيّ بلا واجهة، فيُختبر وحده.
///
/// الموقع يصل كلّ ثلاث ثوانٍ تقريبًا. رسمُه كما يصل يجعل السيارة تقفز
/// قفزاتٍ من عشرات الأمتار، والزبون يقرأ القفز «تطبيقًا معطوبًا». فننزلق
/// بين الموضعين في مدّةٍ تقارب فترة النبضة، فتصل السيارة إلى الموضع
/// الجديد قبل أن يصل الذي بعده بقليل.
library;

import 'dart:math' as math;

import 'package:soum_core/soum_core.dart';

/// أبعد من هذا قفزةٌ لا حركة — عودةٌ بعد انقطاع أو تصحيح GPS. تُرسم فورًا:
/// انزلاقُ سيارةٍ كيلومترين في ثانيتين عبر البيوت أسوأ من قفزة.
const teleportMeters = 1500.0;

/// أقلّ من هذا ارتعاشُ GPS لسيارة واقفة، لا يُغيّر اتجاهها.
const headingNoiseMeters = 4.0;

double distanceMeters(GeoPoint a, GeoPoint b) {
  const r = 6371000.0;
  final dLat = _rad(b.lat - a.lat);
  final dLng = _rad(b.lng - a.lng);
  final h = math.pow(math.sin(dLat / 2), 2) +
      math.cos(_rad(a.lat)) * math.cos(_rad(b.lat)) * math.pow(math.sin(dLng / 2), 2);
  return 2 * r * math.asin(math.min(1, math.sqrt(h)));
}

/// الاتجاه من [a] إلى [b] بالدرجات، 0 = شمال، 90 = شرق.
double bearingDegrees(GeoPoint a, GeoPoint b) {
  final lat1 = _rad(a.lat);
  final lat2 = _rad(b.lat);
  final dLng = _rad(b.lng - a.lng);
  final y = math.sin(dLng) * math.cos(lat2);
  final x = math.cos(lat1) * math.sin(lat2) -
      math.sin(lat1) * math.cos(lat2) * math.cos(dLng);
  return (_deg(math.atan2(y, x)) + 360) % 360;
}

GeoPoint lerpGeo(GeoPoint a, GeoPoint b, double t) =>
    GeoPoint(a.lat + (b.lat - a.lat) * t, a.lng + (b.lng - a.lng) * t);

/// أقصر دوران بين زاويتين — من 350 إلى 10 عشرون درجة لا 340.
double lerpAngle(double from, double to, double t) {
  final delta = ((to - from + 540) % 360) - 180;
  return (from + delta * t + 360) % 360;
}

/// مسار علامة واحدة: من أين، إلى أين، ومتى بدأ.
class MarkerMotion {
  MarkerMotion(GeoPoint position, {double heading = 0})
      : _from = position,
        _to = position,
        _fromHeading = heading,
        _toHeading = heading;

  GeoPoint _from;
  GeoPoint _to;
  double _fromHeading;
  double _toHeading;
  Duration _start = Duration.zero;
  Duration _duration = Duration.zero;

  GeoPoint get target => _to;

  /// موضعٌ جديد وصل عند [now]. الانزلاق يبدأ من حيث العلامة **الآن** لا من
  /// الهدف السابق — وإلّا عادت خطوةً إلى الوراء حين تصل نبضتان متقاربتان.
  void retarget(
    GeoPoint next,
    Duration now, {
    required Duration duration,
    double? heading,
  }) {
    if (next == _to) return;
    final current = positionAt(now);
    final currentHeading = headingAt(now);
    final jump = distanceMeters(current, next);

    _fromHeading = currentHeading;
    if (heading != null) {
      _toHeading = heading;
    } else if (jump >= headingNoiseMeters) {
      _toHeading = bearingDegrees(current, next);
    }

    if (jump > teleportMeters) {
      _from = next;
      _to = next;
      _fromHeading = _toHeading;
      _duration = Duration.zero;
    } else {
      _from = current;
      _to = next;
      _duration = duration;
    }
    _start = now;
  }

  double _progress(Duration now) {
    if (_duration == Duration.zero) return 1;
    final t = (now - _start).inMicroseconds / _duration.inMicroseconds;
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    // تباطؤ عند الوصول: السيارة تهدأ ولا تتوقّف فجأة.
    return 1 - math.pow(1 - t, 2).toDouble();
  }

  bool isMoving(Duration now) => _progress(now) < 1;

  GeoPoint positionAt(Duration now) => lerpGeo(_from, _to, _progress(now));

  double headingAt(Duration now) {
    // الدوران أسرع من الانزلاق: السيارة تستدير أوّلًا ثمّ تمضي.
    final t = math.min(1.0, _progress(now) * 3);
    return lerpAngle(_fromHeading, _toHeading, t);
  }
}

double _rad(double deg) => deg * math.pi / 180;
double _deg(double rad) => rad * 180 / math.pi;
