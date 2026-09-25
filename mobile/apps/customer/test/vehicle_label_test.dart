// بطاقة السيارة على الخريطة: اسم السائق الأوّل، ومقاعد المشتركة نقاطًا.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_customer/features/map/vehicle_marker.dart';

void main() {
  group('الاسم الأوّل', () {
    test('يأخذ الكلمة الأولى من الاسم الكامل', () {
      expect(driverFirstName('أحمد محمد الخطيب'), 'أحمد');
      expect(driverFirstName('  سامر   '), 'سامر');
    });

    test('اسمٌ فارغ يبقى فارغًا — البطاقة تعرض السيارة بدله', () {
      expect(driverFirstName(''), '');
      expect(driverFirstName('   '), '');
    });
  });

  group('الاسم المختصر قبل القبول', () {
    test('الاسم الأوّل وأوّل حرف من الثاني', () {
      expect(driverShortName('محمد عبد الله'), 'محمد ع.');
      expect(driverShortName('  سامر   خليل '), 'سامر خ.');
    });

    test('اسمٌ واحد يبقى كما هو، والفارغ فارغ', () {
      expect(driverShortName('سامر'), 'سامر');
      expect(driverShortName(''), '');
    });
  });

  group('نقاط المقاعد', () {
    // الممتلئة مصمتة (لها لون تعبئة)، والشاغرة إطارٌ بلا تعبئة.
    (int taken, int free) dots(WidgetTester tester) {
      final decorations = tester
          .widgetList<Container>(find.descendant(
            of: find.byType(SeatDots),
            matching: find.byType(Container),
          ))
          .map((c) => c.decoration! as BoxDecoration);
      final taken = decorations.where((d) => d.color != null).length;
      return (taken, decorations.length - taken);
    }

    Future<void> pump(WidgetTester tester, {required int occupied, required int total}) =>
        tester.pumpWidget(
          Directionality(
            textDirection: TextDirection.rtl,
            child: Center(
              child: SeatDots(occupied: occupied, total: total, color: Colors.black),
            ),
          ),
        );

    testWidgets('راكبان من أربعة: نقطتان ممتلئتان ونقطتان شاغرتان', (tester) async {
      await pump(tester, occupied: 2, total: 4);
      expect(dots(tester), (2, 2));
    });

    testWidgets('ركّابٌ أكثر من المقاعد لا يرسمون نقاطًا زائدة', (tester) async {
      await pump(tester, occupied: 6, total: 4);
      expect(dots(tester), (4, 0));
    });

    testWidgets('السرفيس يُختصر إلى ثماني نقاط', (tester) async {
      await pump(tester, occupied: 3, total: 14);
      expect(dots(tester), (3, SeatDots.maxDots - 3));
    });
  });
}
