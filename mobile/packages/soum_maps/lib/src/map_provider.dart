/// واجهة مزوّد الخرائط.
///
/// لماذا طبقةٌ مجرّدة بدل استعمال المزوّد مباشرةً:
///
/// الخرائط في هذا المشروع ليست شاشةً واحدة. هي الشاشة الرئيسية، وشاشة
/// اختيار الوجهة، وشاشة البحث بدائرتها، وشاشة التتبّع بسيارتها المتحرّكة،
/// وشاشة المسار المسجَّل بعد الرحلة — خمس شاشات في تطبيقين. استبدال
/// المزوّد لاحقًا بلا هذه الطبقة يعني إعادة كتابة عشر شاشات.
///
/// والاستبدال ليس فرضيًّا: النسخة الحالية تعمل ببلاطات OpenStreetMap —
/// بلا مفتاح وبلا فوترة، وهو ما يناسب مرحلةً قبل أيّ اشتراك مدفوع. ويوم
/// يُشترى اشتراك Google Maps يصير التبديل تنفيذًا ثانيًا لهذه الواجهة
/// وسطرَ إعداد، لا مشروعًا.
///
/// القاعدة المقابلة، وتُفحص آليًّا في اختبارات soum_maps: **لا شاشة
/// تستورد `flutter_map` مباشرةً**. الشاشات تتكلّم `SoumMap` وحدها.
library;

import 'package:flutter/widgets.dart';
import 'package:soum_core/soum_core.dart';

/// علامة على الخريطة.
class MapMarker {
  const MapMarker({
    required this.id,
    required this.position,
    required this.builder,
    this.size = const Size(44, 44),
    this.rotationDegrees,
    this.animate = false,
  });

  /// معرّف ثابت — به تُحدَّث العلامة بدل إعادة بنائها، فلا ترتجف السيارة
  /// على الشاشة مع كلّ نبضة موقع كلّ ثلاث ثوانٍ.
  final String id;

  final GeoPoint position;
  final WidgetBuilder builder;
  final Size size;

  /// لتدوير سهم اتجاه السيارة — `route_bearing` من الخادم.
  final double? rotationDegrees;

  /// سيارةٌ تتحرّك: تنزلق من موضعها السابق إلى الجديد بدل أن تقفز،
  /// واتجاهها يُقرأ من حركتها عبر [MarkerHeading] لا يُدار الشكل كلّه —
  /// فتدور السيارة وتبقى بطاقتها فوقها مقروءة.
  final bool animate;
}

/// اتجاه سير العلامة المتحرّكة بالدرجات (0 = شمال، باتّجاه عقارب الساعة).
///
/// يُمرَّر لبانِي العلامة بدل تدويرها كاملةً: السيارة تدور، والنصّ فوقها
/// لا ينقلب رأسًا على عقب حين تتّجه جنوبًا.
class MarkerHeading extends InheritedWidget {
  const MarkerHeading({super.key, required this.degrees, required super.child});

  final double degrees;

  static double? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<MarkerHeading>()?.degrees;

  @override
  bool updateShouldNotify(MarkerHeading old) => old.degrees != degrees;
}

/// خطّ على الخريطة — مسار رحلة أو مسار مسجَّل.
class MapPolyline {
  const MapPolyline({
    required this.points,
    required this.color,
    this.width = 4,
    this.isDashed = false,
  });

  final List<GeoPoint> points;
  final Color color;
  final double width;

  /// متقطّع = تقديريّ لا مسار حقيقيّ. يُستعمل حين يكون `route_source`
  /// تقديرًا — وهو تمييزٌ بصريّ يوازي «سعر تقريبي» في النصّ.
  final bool isDashed;
}

/// دائرة — نطاق البحث بـ`matching_radius_km`، أو نطاق الوصول بالأمتار.
class MapCircle {
  const MapCircle({
    required this.center,
    required this.radiusMeters,
    required this.color,
    required this.borderColor,
    this.borderWidth = 1.5,
  });

  final GeoPoint center;
  final double radiusMeters;
  final Color color;
  final Color borderColor;
  final double borderWidth;
}

/// الموضع الأوّل للخريطة.
///
/// الاسم ليس MapCamera تجنّبًا لتصادم مع صنف في flutter_map — وهو
/// أوضح أصلًا: هذه نقطة البدء لا الكاميرا الحيّة.
class MapStart {
  const MapStart({required this.center, required this.zoom});

  final GeoPoint center;
  final double zoom;
}

/// ما تراه الشاشة الآن — يُستعمل لتبديل خليّة السوق مع حركة الخريطة.
class MapViewport {
  const MapViewport({
    required this.center,
    required this.zoom,
    required this.northEast,
    required this.southWest,
  });

  final GeoPoint center;
  final double zoom;
  final GeoPoint northEast;
  final GeoPoint southWest;
}

/// التحكّم بالخريطة من خارج شجرة العرض.
abstract interface class SoumMapController {
  void moveTo(GeoPoint center, {double? zoom});

  /// يضبط الكاميرا لتسع النقاط كلّها — الانطلاق والوجهة والسيارة.
  void fitPoints(List<GeoPoint> points, {EdgeInsets padding});

  MapViewport? get viewport;
}
