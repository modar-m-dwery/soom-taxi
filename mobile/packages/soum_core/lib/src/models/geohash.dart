/// ترميز geohash — منقول حرفيًّا عن `locations/geohash.py` في الخادم.
///
/// **لماذا هذا الملفّ موجود أصلًا، وهو ما يجب ألّا يبقى هكذا:**
///
/// دليل التكامل يقول في §9.1: «الخليّة تأتي جاهزة في ردود الخادم». وهي
/// لا تأتي. فحصُ كلّ مُسلسِل ونقطة نهاية في المشروع لا يُظهر حقل
/// `cell_id` في أيّ استجابة — يُحسب في `LocationService` ويُخزَّن في
/// Redis لحضور السائق، ولا يخرج إلى العميل.
///
/// والتطبيق يحتاجه: الاشتراك في `/ws/marketplace/{cell}/` لا يتمّ بلا
/// معرّف خليّة، وهو مدخل الخريطة الحيّة كلّها.
///
/// فلم يبقَ إلّا حسابه هنا. والشرط أن يكون الحساب **مطابقًا بتًّا ببتّ**:
/// خليّة تختلف بحرف واحد هي غرفة لا أحد فيها، وخريطةٌ فارغة بلا خطأ —
/// أسوأ من عطل مرئيّ. لذلك اختبار هذا الملفّ يقارن بقيم أخرجها الخادم
/// نفسه: ‏`JAB:sy390vj` لجبلة بدقّة 7، و`LAT:sy36nh` للاذقية بدقّة 6.
///
/// **التوصية:** إضافة `cell_id` إلى استجابة `/config/` (أو أيّ نقطة
/// تعرف موقع المستخدم) تُلغي الحاجة إلى هذا الملفّ كاملًا، وتُزيل خطر
/// تباعد تنفيذين مع الوقت. حتّى ذلك الحين، أيّ تعديل في
/// `locations/geohash.py` يجب أن يُنسخ إلى هنا.
library;

import '../config/app_config.dart' show AppConfig;
import 'geo.dart';

abstract final class Geohash {
  static const _base32 = '0123456789bcdefghjkmnpqrstuvwxyz';

  /// نفس الخوارزمية القياسية التي يستعملها الخادم: تقسيم يبدأ بخطّ الطول.
  static String encode(double lng, double lat, {int precision = 7}) {
    var latLow = -90.0, latHigh = 90.0;
    var lngLow = -180.0, lngHigh = 180.0;

    final out = StringBuffer();
    var bit = 0;
    var ch = 0;
    var even = true;

    while (out.length < precision) {
      if (even) {
        final mid = (lngLow + lngHigh) / 2;
        if (lng > mid) {
          ch = (ch << 1) | 1;
          lngLow = mid;
        } else {
          ch = ch << 1;
          lngHigh = mid;
        }
      } else {
        final mid = (latLow + latHigh) / 2;
        if (lat > mid) {
          ch = (ch << 1) | 1;
          latLow = mid;
        } else {
          ch = ch << 1;
          latHigh = mid;
        }
      }

      even = !even;
      bit++;

      if (bit == 5) {
        out.write(_base32[ch]);
        bit = 0;
        ch = 0;
      }
    }

    return out.toString();
  }
}

extension MarketplaceCell on AppConfig {
  /// معرّف خليّة السوق لنقطة — `JAB:sy390vj`.
  ///
  /// `null` خارج مناطق الخدمة: لا `area_code` يعني لا خليّة، والاشتراك
  /// بغرفة مخترَعة يصمت بلا خطأ.
  String? cellIdFor(GeoPoint point) {
    final code = areaCode;
    if (code == null || code.isEmpty) return null;

    final cell = Geohash.encode(
      point.lng,
      point.lat,
      precision: geometry.marketplaceCellPrecision,
    );
    return '$code:$cell';
  }
}
