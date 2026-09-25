// أمر كاميرا قبل أوّل رسم — يجب أن يُؤجَّل لا أن ينفجر.
//
// عُثر على العطل على محاكٍ يعمل: الموقع المخزَّن يعود قبل أوّل إطار،
// فيرمي `moveTo` استثناءً غير معالَج وتتوقّف سلسلة الإقلاع عنده.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';

void main() {
  const jableh = GeoPoint(35.3600, 35.9000);
  const latakia = GeoPoint(35.5317, 35.7797);

  test('moveTo قبل الرسم لا يرمي', () {
    final controller = OsmMapController();
    expect(() => controller.moveTo(jableh, zoom: 15), returnsNormally);
    expect(() => controller.fitPoints(const [jableh, latakia]), returnsNormally);
  });

  testWidgets('الأمر المؤجَّل يُطبَّق عند جاهزية الخريطة', (tester) async {
    final controller = OsmMapController();
    // يُستدعى قبل أن تُبنى الخريطة أصلًا.
    controller.moveTo(latakia, zoom: 13);

    await tester.pumpWidget(
      MaterialApp(
        home: SoumMap(
          controller: controller,
          initialCamera: const MapStart(center: jableh, zoom: 15),
        ),
      ),
    );
    await tester.pump();

    final viewport = controller.viewport;
    expect(viewport, isNotNull, reason: 'الخريطة رُسمت فالكاميرا موجودة');
    expect(viewport!.center.lat, closeTo(latakia.lat, 0.001));
    expect(viewport.center.lng, closeTo(latakia.lng, 0.001));
    expect(viewport.zoom, 13);
  });
}
