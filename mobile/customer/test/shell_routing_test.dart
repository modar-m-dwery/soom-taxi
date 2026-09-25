// T3.7 و T2.3 — الشاشة تتبع المرحلة.
//
// ما يقيسه هذا الملفّ ليس أنّ الشاشات تُبنى، بل أنّ **الشاشة تتبدّل مع
// الحالة الواصلة**. رحلةٌ أُلغيت من الإدارة تغيّر `stage` فتتغيّر الشاشة
// بلا تنقّل يدويّ — وهو ما يجعل «حساب الحالة محلّيًّا» غير ممكن أصلًا.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_customer/features/ride/ride_state.dart';

RideRequest ride(String status) => RideRequest.fromJson({
      'id': 2702,
      'status': status,
      'mode': 'standard',
      'trip_category': 'city',
      'passenger_count': 1,
      'currency': 'SYP',
      'route_source': 'provider',
      'created_at': '2026-09-14T20:00:00Z',
    });

Trip trip(String status) => Trip.fromJson({
      'id': 5,
      'ride': 2702,
      'status': status,
      'driver': 1,
      'driver_name': 'سائق',
      'currency': 'SYP',
      'final_fare': '5512.00',
      'created_at': '2026-09-14T20:00:00Z',
    });

Payment payment() => Payment.fromJson({
      'id': 9,
      'trip_id': 5,
      'ride_id': 2702,
      'amount': '5512.00',
      'platform_fee': '0.00',
      'driver_net': '5512.00',
      'amount_refunded': '0.00',
      'refundable_amount': '0.00',
      'currency': 'SYP',
      'gateway_code': 'cash',
      'status': 'pending',
    });

void main() {
  group('المرحلة مشتقّة من الحالات الواصلة', () {
    test('بلا طلب: الرئيسية', () {
      expect(const RideArc().stage, ResumeStage.idle);
      expect(const RideArc().isIdle, isTrue);
    });

    test('searching ← البحث، offers_received ← اختيار عرض', () {
      expect(RideArc(ride: ride('searching')).stage, ResumeStage.searching);
      expect(
        RideArc(ride: ride('offers_received')).stage,
        ResumeStage.choosingOffer,
      );
    });

    test('الرحلة أدقّ من الطلب حين توجد — كما في الخادم', () {
      // الطلب يقول driver_selected والرحلة تقول in_progress: الرحلة تفوز،
      // وهو نفس ترتيب `_resolve_stage` في trips/services/resume.py.
      final arc = RideArc(
        ride: ride('driver_selected'),
        trip: trip('in_progress'),
      );
      expect(arc.stage, ResumeStage.inProgress);
    });

    test('كلّ حالات الرحلة تُخرِج مرحلة تتبّع', () {
      const expected = {
        'created': ResumeStage.driverAssigned,
        'driver_arriving': ResumeStage.driverArriving,
        'driver_arrived': ResumeStage.driverArrived,
        'in_progress': ResumeStage.inProgress,
      };

      expected.forEach((status, stage) {
        final arc = RideArc(ride: ride('driver_selected'), trip: trip(status));
        expect(arc.stage, stage, reason: status);
        expect(arc.stage.isOnTrip, isTrue);
      });
    });

    test('رحلة انتهت ولم تُدفع: شاشة الدفع لا الرئيسية', () {
      final arc = RideArc(pendingPayment: payment());
      expect(arc.stage, ResumeStage.awaitingPayment);
      expect(arc.isIdle, isFalse);
    });

    test('رحلة انتهت ودُفعت: الرئيسية', () {
      expect(const RideArc().stage, ResumeStage.idle);
    });

    test('حالة لا يعرفها هذا الإصدار لا تُسقط الشاشة', () {
      final arc = RideArc(ride: ride('some_future_status'));
      expect(arc.stage, ResumeStage.idle);
    });
  });

  group('العروض', () {
    RideOffer offer(int id, String fare, int eta) => RideOffer.fromJson({
          'id': id,
          'ride': 2702,
          'driver_id': id,
          'driver_name': 'سائق $id',
          'gross_fare': fare,
          'eta_minutes': eta,
          'status': 'pending',
          'expires_at': '2026-09-14T20:01:00Z',
          'created_at': '2026-09-14T20:00:30Z',
        });

    test('حالة الخطأ تُمحى عند التحديث التالي', () {
      final withError = const RideArc().copyWith(
        lastError: ApiException(
          statusCode: 409,
          code: ApiErrorCode.conflict,
          detail: 'x',
        ),
        clearError: false,
      );
      expect(withError.lastError, isNotNull);

      final after = withError.copyWith(offers: [offer(1, '5000.00', 3)]);
      expect(after.lastError, isNull,
          reason: 'خطأٌ معلّق بعد نجاح العملية التالية يجعل الشاشة تكذب');
    });

    test('التهدئة تُحفظ ثمّ تُرفع', () {
      final withCooldown = const RideArc().copyWith(cooldownDrivers: {7});
      expect(withCooldown.cooldownDrivers, contains(7));

      final lifted = withCooldown.copyWith(cooldownDrivers: const {});
      expect(lifted.cooldownDrivers, isEmpty);
    });
  });
}
