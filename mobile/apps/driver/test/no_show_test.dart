// «الزبون لم يحضر» يرسل رمزه، ورحلة الردّ تحمل التعويض.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  test('الرحلة الملغاة بعدم حضور تقرأ التعويض', () {
    final trip = Trip.fromJson(const {
      'id': 9,
      'ride': 41,
      'status': 'cancelled',
      'driver': 3,
      'currency': 'SYP',
      'final_fare': '0.00',
      'driver_compensation': '4000.00',
      'created_at': '2026-09-25T20:00:00Z',
    });
    expect(trip.driverCompensation, Money.parse('4000.00'));
  });

  test('رحلةٌ بلا تعويض: null لا صفر', () {
    final trip = Trip.fromJson(const {
      'id': 9,
      'ride': 41,
      'status': 'cancelled',
      'driver': 3,
      'currency': 'SYP',
      'final_fare': '0.00',
      'driver_compensation': null,
      'created_at': '2026-09-25T20:00:00Z',
    });
    expect(trip.driverCompensation, isNull);
  });

  test('زرّ عدم الحضور يرسل رمز customer_no_show لا نصًّا وحده', () {
    final source = File('lib/features/work/work_controller.dart').readAsStringSync();
    final start = source.indexOf('reportNoShow(');
    expect(start, greaterThan(-1));
    expect(source.substring(start, start + 700),
        contains('DriverCancelReason.customerNoShow'));
  });

  test('المهلة من الإعداد لا رقمٌ مثبَّت', () {
    final source = File('lib/features/run/run_screen.dart').readAsStringSync();
    expect(source, contains('config.timings.cancelWaitMinutes'));
  });
}
