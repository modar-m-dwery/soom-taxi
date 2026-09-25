// T2.4 — الاتجاه والخطّ والأرقام الجدولية، مقيسة على شجرة مرسومة فعلًا.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

Widget _wrap(Widget child) => ProviderScope(
      child: MaterialApp(
        theme: SoumTheme.light(),
        locale: const Locale('ar'),
        supportedLocales: SoumStrings.supportedLocales,
        localizationsDelegates: SoumStrings.localizationsDelegates,
        home: Scaffold(body: child),
      ),
    );

void main() {
  testWidgets('الاتجاه من اليمين في الواجهة العربية', (tester) async {
    await tester.pumpWidget(_wrap(const SizedBox()));

    final direction = Directionality.of(
      tester.element(find.byType(Scaffold)),
    );
    expect(direction, TextDirection.rtl);
  });

  testWidgets('المبلغ يُعرض بأرقام جدولية وبرمز العملة', (tester) async {
    await tester.pumpWidget(_wrap(MoneyText(Money.parse('5512.00'))));
    await tester.pumpAndSettle();

    final text = tester.widget<Text>(find.byType(Text).first);
    final span = text.textSpan! as TextSpan;
    final amount = span.children!.first as TextSpan;

    expect(
      amount.style!.fontFeatures,
      contains(const FontFeature.tabularFigures()),
      reason: 'بخطّ متناسب يرتجف السطر مع كلّ تغيّر رقم',
    );
    expect(find.textContaining('ل.س', findRichText: true), findsOneWidget);
  });

  testWidgets('بطاقة الأجرة تقول «سعر تقريبي» حين لا مسار', (tester) async {
    final fare = FareBreakdown.fromJson(const {
      'base_fare': '4000.00',
      'distance_fare': '1272.00',
      'time_fare': '240.00',
      'gross_fare': '5512.00',
      'platform_fee': '0.00',
      'customer_total': '5512.00',
      'driver_net': '5512.00',
      'currency': 'SYP',
      'surge_multiplier': '1.00',
    });

    await tester.pumpWidget(_wrap(
      SingleChildScrollView(
        child: FareCard(fare: fare, routeSource: RouteSource.estimated),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('سعر تقريبي'), findsOneWidget);
    expect(find.text('سعر المسار'), findsNothing);

    // عمولة صفر: لا سطر يثير سؤالًا بلا داعٍ.
    expect(find.text('عمولة المنصّة'), findsNothing);
  });

  testWidgets('وبـ«سعر المسار» حين يأتي من المزوّد', (tester) async {
    final fare = FareBreakdown.fromJson(const {
      'base_fare': '4000.00', 'distance_fare': '1272.00', 'time_fare': '240.00',
      'gross_fare': '5512.00', 'platform_fee': '0.00',
      'customer_total': '5512.00', 'driver_net': '5512.00',
      'currency': 'SYP', 'surge_multiplier': '1.00',
    });

    await tester.pumpWidget(_wrap(
      SingleChildScrollView(
        child: FareCard(fare: fare, routeSource: RouteSource.provider),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('سعر المسار'), findsOneWidget);
  });

  testWidgets('عمولة غير صفرية تُعرض — الشرط على القيمة لا على النسخة',
      (tester) async {
    final fare = FareBreakdown.fromJson(const {
      'base_fare': '4000.00', 'distance_fare': '1272.00', 'time_fare': '240.00',
      'gross_fare': '5512.00', 'platform_fee': '551.20',
      'customer_total': '5512.00', 'driver_net': '4960.80',
      'currency': 'SYP', 'surge_multiplier': '1.00',
    });

    await tester.pumpWidget(_wrap(
      SingleChildScrollView(
        child: FareCard(fare: fare, routeSource: RouteSource.provider),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('عمولة المنصّة'), findsOneWidget);
    expect(find.text('ما يقبضه السائق'), findsOneWidget);
  });

  testWidgets('خطأ الشبكة يعرض رسالة التطبيق، وخطأ الخادم يعرض نصّه',
      (tester) async {
    await tester.pumpWidget(_wrap(ApiErrorView(
      failure: ApiException(
        statusCode: 0,
        code: ApiErrorCode.networkUnavailable,
        detail: 'لا اتصال بالإنترنت.',
      ),
    )));
    await tester.pumpAndSettle();
    expect(find.text('لا اتصال بالإنترنت'), findsOneWidget);

    await tester.pumpWidget(_wrap(ApiErrorView(
      failure: ApiException(
        statusCode: 400,
        code: ApiErrorCode.driverNotEligible,
        detail: 'وثيقة التأمين منتهية الصلاحية.',
        requestId: 'ce62f08a791b',
      ),
    )));
    await tester.pumpAndSettle();

    // §12.3: «اعرض السبب من detail لا رسالة عامّة».
    expect(find.text('وثيقة التأمين منتهية الصلاحية.'), findsOneWidget);
    expect(find.textContaining('ce62f08a791b'), findsOneWidget);
  });

  testWidgets('العدّاد يتناقص ويُنادي onExpired مرّة واحدة', (tester) async {
    var expiredCount = 0;
    var fakeNow = DateTime.utc(2026, 9, 14, 20, 0, 0);

    // الساعة تُقدَّم مع المؤقّت. بلا ذلك يُطلَق المؤقّت في الاختبار
    // بينما ساعة النظام لم تتحرّك — فيمرّ اختبارٌ لم يقِس شيئًا.
    {
      await tester.pumpWidget(_wrap(SoumCountdown(
        deadline: fakeNow.add(const Duration(seconds: 2)),
        clock: ServerClock.fixed(() => fakeNow),
        onExpired: () => expiredCount++,
        builder: (_, seconds) =>
            Text('$seconds', textDirection: TextDirection.ltr),
      )));

      expect(find.text('2'), findsOneWidget);

      fakeNow = fakeNow.add(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      expect(find.text('1'), findsOneWidget);

      fakeNow = fakeNow.add(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      expect(find.text('0'), findsOneWidget);
      expect(expiredCount, 1);

      fakeNow = fakeNow.add(const Duration(seconds: 3));
      await tester.pump(const Duration(seconds: 3));
      expect(expiredCount, 1, reason: 'مرّة واحدة لا مع كلّ إطار');
    }
  });
}
