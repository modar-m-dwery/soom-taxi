// «سوم» بنمط inDrive — حدود العميل تقع داخل حدود الخادم دائمًا.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

RideRequest ride({String gross = '10000.00', String? proposed, String? cap}) =>
    RideRequest.fromJson({
      'id': 7,
      'status': 'searching',
      'mode': 'standard',
      'trip_category': 'city',
      'passenger_count': 1,
      'currency': 'SYP',
      'route_source': 'provider',
      'gross_fare': gross,
      'customer_total': gross,
      'driver_net': gross,
      'fare_cap': cap,
      'customer_proposed_fare': proposed,
      'created_at': '2026-09-25T20:00:00Z',
    });

Money m(String v) => Money.parse(v);

void main() {
  final rules = FareProposalRules.defaults;

  test('يقرأ القواعد من إعداد المنطقة', () {
    final parsed = FareProposalRules.fromJson(const {
      'customer_proposal_min_ratio': '0.80',
      'customer_proposal_counter_ratio': '1.30',
      'customer_proposal_step': '250.00',
    });
    expect(parsed.minRatio.toString(), '0.8');
    expect(parsed.step.toString(), '250');
    expect(FareProposalRules.fromJson(const {}), FareProposalRules.defaults);
  });

  test('الأرضيّة الأولى 70٪ من التسعيرة مقرَّبةً لأعلى إلى الخطوة', () {
    expect(rules.minFor(ride(gross: '10000.00')), m('7000'));
    // 70٪ من 9100 = 6370 ← 6500: فوق أرضيّة الخادم لا على حافّتها.
    expect(rules.minFor(ride(gross: '9100.00')), m('6500'));
  });

  test('بعد العرض: يُرفع فقط، خطوةً على الأقلّ', () {
    expect(rules.minFor(ride(proposed: '8000.00')), m('8500'));
    expect(rules.suggestedFor(ride(proposed: '8000.00')), m('8500'));
  });

  test('نقطة البداية: التسعيرة نفسها', () {
    expect(rules.suggestedFor(ride(gross: '9100.00')), m('9500'));
  });

  test('السقف: سقف المنطقة، وإلّا ثلاثة أضعاف التسعيرة', () {
    expect(rules.maxFor(ride(cap: '15000.00')), m('15000'));
    expect(rules.maxFor(ride()), m('30000'));
  });

  test('عروض السائق الجاهزة ضمن سقف 150٪ وبلا تكرار', () {
    expect(
      rules.quickCounters(ride(proposed: '8000.00')),
      [m('8000'), m('8500'), m('9000'), m('9500')],
    );
    // سقف المنطقة أدنى من 150٪: العروض تتوقّف عنده.
    expect(
      rules.quickCounters(ride(proposed: '8000.00', cap: '8600.00')),
      [m('8000'), m('8500')],
    );
    expect(rules.counterCap(ride(proposed: '8000.00')), m('12000'));
  });
}
