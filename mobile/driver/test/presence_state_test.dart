// T4.4 — التمييز بين «متّصل» و«داخل المطابقة».
//
// هذا التمييز هو خلاصة أهمّ اكتشاف في هذا المشروع: `go-online` ينجح،
// والسائق يرى «متّصل»، ولا يصله طلب واحد — لأنّ المطابقة تشترط
// `last_location_at` حديثًا ولا يتحدّث إلّا بنبضة موقع.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_driver/features/presence/presence_state.dart';

void main() {
  test('متوقّف: لا متّصل ولا مطابَق', () {
    const state = PresenceState();
    expect(state.isOnline, isFalse);
    expect(state.isMatchable, isFalse);
  });

  test('متّصل بلا نبضة: متّصل ولكن ليس مطابَقًا', () {
    const state = PresenceState(stage: PresenceStage.onlineNoHeartbeat);
    expect(state.isOnline, isTrue);
    expect(state.isMatchable, isFalse,
        reason: 'go-online وحده لا يُدخل السائق في المطابقة');
  });

  test('بعد أوّل ack: مطابَق', () {
    final state = PresenceState(
      stage: PresenceStage.matchable,
      lastAck: DateTime.now(),
    );
    expect(state.isMatchable, isTrue);
  });

  test('انقطاع النبض يُخرجه من المطابقة ويُبقيه متّصلًا ظاهريًّا', () {
    const state = PresenceState(stage: PresenceStage.stale);
    expect(state.isOnline, isTrue, reason: 'الخادم لم يُوقفه بعد');
    expect(state.isMatchable, isFalse, reason: 'خرج من الأسطول المرئي');
  });

  group('المانع مصنَّف لا مكتوب', () {
    test('إذن الموقع', () {
      const state = PresenceState(blocker: PresenceBlocker.locationUnavailable);
      expect(state.blocker, PresenceBlocker.locationUnavailable);
    });

    test('رفض الخادم يحتفظ بنصّه للعرض', () {
      final state = PresenceState(
        blocker: PresenceBlocker.serverRefused,
        failure: ApiException(
          statusCode: 400,
          code: ApiErrorCode.driverNotEligible,
          detail: 'وثيقة التأمين منتهية الصلاحية.',
        ),
      );
      expect(state.failure!.detail, contains('التأمين'),
          reason: '§12.3: اعرض السبب من detail لا رسالة عامّة');
    });

    test('clearFailure يمحو المانع معه', () {
      final state = PresenceState(
        blocker: PresenceBlocker.serverRefused,
        failure: ApiException(statusCode: 400, code: 'x', detail: 'y'),
      ).copyWith(stage: PresenceStage.matchable, clearFailure: true);

      expect(state.blocker, PresenceBlocker.none);
      expect(state.failure, isNull);
    });
  });
}
