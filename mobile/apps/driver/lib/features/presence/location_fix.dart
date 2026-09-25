import 'package:geolocator/geolocator.dart';
import 'package:soum_core/soum_core.dart';

/// نقطة موقع بما يرافقها من قراءة الـGPS — لا إحداثيّتان وحدهما.
///
/// `mocked` هو السبب الذي وُجد له هذا الصنف: أندرويد يعلن حين يأتي الموقع
/// من تطبيق تزييف (Fake GPS)، والخادم يرفض هذه النقطة ويسجّلها على السائق
/// في نظام النزاهة. بدون إرساله لا يرى الخادم التزييف أبدًا — السائق يضع
/// نفسه قرب طلباتٍ ليس قربها ويأخذها من سائقين حقيقيّين.
///
/// والسرعة والاتجاه والدقّة تُحفظ مع نقاط مسار الرحلة، وبها يُقاس تطويل
/// الطريق وتُفهم قفزات الموقع حين يُراجع موظّفٌ قضيّة.
class LocationFix {
  const LocationFix({
    required this.point,
    this.speed,
    this.heading,
    this.accuracy,
    this.mocked = false,
  });

  factory LocationFix.fromPosition(Position position) {
    final speed = position.speed;
    final heading = position.heading;
    final accuracy = position.accuracy;

    return LocationFix(
      point: GeoPoint(position.latitude, position.longitude),
      // سالبٌ يعني «غير معروف» في iOS، وصفرٌ بلا `hasHeading` في أندرويد
      // يعني أنّ الجهاز لم يحسب اتجاهًا — لا أنّ السيارة تتّجه شمالًا.
      speed: speed.isFinite && speed >= 0 ? speed : null,
      heading: heading.isFinite &&
              heading >= 0 &&
              heading <= 360 &&
              (position.hasHeading || heading > 0)
          ? heading
          : null,
      accuracy: accuracy.isFinite && accuracy > 0 ? accuracy : null,
      mocked: position.isMocked,
    );
  }

  final GeoPoint point;

  /// متر في الثانية، كما يقرؤها الجهاز.
  final double? speed;

  /// بالدرجات، صفرٌ شمال وباتّجاه عقارب الساعة.
  final double? heading;

  /// نصف قطر الدقّة بالمتر.
  final double? accuracy;

  /// الموقع من تطبيق تزييف لا من الـGPS.
  final bool mocked;

  /// إطار `location.update` لغرفة السائق.
  Json toFrame() => {
        'type': 'location.update',
        'lat': point.lat,
        'lng': point.lng,
        'speed': ?speed,
        'heading': ?heading,
        'accuracy': ?accuracy,
        // يُرسل دائمًا ولو false: الصريح يميّز تطبيقًا يفحص عن نسخةٍ قديمة
        // لا ترسله أصلًا.
        'mocked': mocked,
      };
}
