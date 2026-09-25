// الطلب ينتهي بغير يد الزبون ← رسالة تقول ما حدث. بيد الزبون ← لا رسالة.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_customer/features/ride/ride_controller.dart';
import 'package:soum_customer/features/ride/ride_state.dart';

void main() {
  test('انقضاء المهلة', () {
    expect(rideEndFor(RealtimeEventType.rideExpired, const {}), RideEnd.expired);
  });

  test('السائق سجّل عدم الحضور', () {
    expect(
      rideEndFor(RealtimeEventType.rideCancelled,
          const {'cancelled_by': 'driver', 'kind': 'no_show'}),
      RideEnd.noShow,
    );
  });

  test('الزبون ألغى بيده: لا رسالة', () {
    expect(
      rideEndFor(RealtimeEventType.rideCancelled,
          const {'cancelled_by': 'customer', 'kind': 'late'}),
      isNull,
    );
  });

  test('الإدارة ألغت', () {
    expect(
      rideEndFor(RealtimeEventType.rideCancelled, const {'cancelled_by': 'admin'}),
      RideEnd.cancelledByOther,
    );
  });
}
