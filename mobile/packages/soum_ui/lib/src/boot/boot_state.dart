/// تسلسل الإقلاع — الترتيب مفروض لا مقترح.
///
/// §12.1 في دليل التكامل يضع ثلاثة بنود من خمسة على هذا التسلسل تحديدًا:
///
/// > `GET /config/` يُقرأ عند كلّ إقلاع، ولا رقم من أرقامه مثبَّت في الشيفرة
/// > `device_id` ثابت ومحفوظ — لا يُولَّد في كلّ نداء
/// > `/me/active-ride/` هو أوّل نداء بعد المصادقة في كلّ إقلاع
///
/// والترتيب بينها ليس تفصيلًا:
///
/// **الإعداد قبل المصادقة** لأنّ شاشة الهاتف نفسها تحتاجه — فئات المركبات
/// وأنصاف الأقطار تُرسم قبل تسجيل الدخول، والنقطة عامّة بلا مصادقة عمدًا.
///
/// **الرحلة القائمة قبل الشاشة الرئيسية** لأنّ الشاشة تتبع الحالة لا العكس.
/// مستخدمٌ أغلق التطبيق والسائق في الطريق يجب أن يعود إلى شاشة التتبّع، لا
/// إلى شاشة طلب رحلة جديدة فوق رحلة قائمة.
///
/// **والدفع المعلّق قبل الرئيسية أيضًا** (§12.3): رحلةٌ انتهت ولم تُدفع
/// تفتح شاشة الدفع. فتح الرئيسية بدلها يجعل الأجرة تختفي من نظر الزبون —
/// وهي لم تُدفع بعد.
library;

import 'package:soum_core/soum_core.dart';

enum BootStep { config, session, activeRide }

sealed class BootState {
  const BootState();
}

class BootLoading extends BootState {
  const BootLoading(this.step);
  final BootStep step;
}

/// الإعداد قُرئ ولا مفتاح — شاشة الهاتف.
class BootNeedsAuth extends BootState {
  const BootNeedsAuth(this.config);
  final AppConfig config;
}

/// كلّ شيء جاهز. `snapshot.stage` يقرّر أيّ شاشة تُفتح.
class BootReady extends BootState {
  const BootReady({
    required this.config,
    required this.user,
    required this.snapshot,
  });

  final AppConfig config;
  final AppUser user;
  final ActiveRideSnapshot snapshot;

  ServerClock get clock => config.clock;
}

/// تعذّر الإقلاع — ولا خبيئة صالحة تُرسم منها شاشة.
class BootFailed extends BootState {
  const BootFailed(this.failure);
  final ApiException failure;
}
