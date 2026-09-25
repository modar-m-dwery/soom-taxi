// القيم المرجعية من الخادم نفسه.
//
// أمر `locations_resolve_test` على الخادم الذي يعمل أخرج:
//
//   [داخل جبلة]    -> area=JAB precision=7 cell_id=JAB:sy390vj
//   [داخل اللاذقية] -> area=LAT precision=6 cell_id=LAT:sy36nh
//
// وهي ما يقيسه هذا الملفّ: تنفيذان لخوارزمية واحدة يجب أن يتّفقا حرفًا
// بحرف، وإلّا اشترك التطبيق في غرفة لا أحد فيها — فتظهر خريطة فارغة بلا
// أيّ خطأ يدلّ على السبب.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  test('جبلة بدقّة 7 تطابق خرج الخادم', () {
    expect(Geohash.encode(35.9, 35.36, precision: 7), 'sy390vj');
  });

  test('اللاذقية بدقّة 6 تطابق خرج الخادم', () {
    expect(Geohash.encode(35.78, 35.53, precision: 6), 'sy36nh');
  });

  test('الدقّة تقصّ ولا تغيّر — خاصّية البادئة في geohash', () {
    final full = Geohash.encode(35.9, 35.36, precision: 8);
    for (var precision = 1; precision <= 8; precision++) {
      expect(
        Geohash.encode(35.9, 35.36, precision: precision),
        full.substring(0, precision),
      );
    }
  });

  test('نقطتان متجاورتان في الخليّة نفسها، وبعيدتان في خليّتين', () {
    const precision = 7;
    final here = Geohash.encode(35.9236, 35.3608, precision: precision);
    final metersAway = Geohash.encode(35.92361, 35.36081, precision: precision);
    final acrossTown = Geohash.encode(35.78, 35.53, precision: precision);

    expect(metersAway, here);
    expect(acrossTown, isNot(here));
  });

  test('المعرّف يحمل رمز المدينة، ويغيب خارج مناطق الخدمة', () {
    AppConfig config({String? area}) => AppConfig.fromJson({
          'area_code': area,
          'area_name': area,
          'resolved_from': area == null ? 'none' : 'coordinates',
          'ride_modes': <String>[],
          'invitation_allowed_modes': <String>[],
          'vehicle_categories': <dynamic>[],
          'timings': <String, dynamic>{},
          'geometry': {'marketplace_cell_precision': 7},
          'pricing': <String, dynamic>{},
          'server_time': '2026-09-14T20:00:00Z',
        });

    expect(
      config(area: 'JAB').cellIdFor(const GeoPoint(35.36, 35.9)),
      'JAB:sy390vj',
    );
    expect(config().cellIdFor(const GeoPoint(35.36, 35.9)), isNull);
  });
}
