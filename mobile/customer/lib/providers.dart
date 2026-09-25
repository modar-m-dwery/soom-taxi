/// المزوّدات الجذرية.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

export 'package:soum_ui/soum_ui.dart' show bootControllerProvider, soumProvider;

/// الإعداد بعد نجاح الإقلاع. الوصول إليه قبل ذلك خطأ برمجيّ لا حالة
/// وقت تشغيل — لذلك يرمي بدل أن يُعيد null يُفحص في عشرين موضعًا.
final configProvider = Provider<AppConfig>((ref) {
  final boot = ref.watch(bootControllerProvider);
  if (boot is BootReady) return boot.config;
  if (boot is BootNeedsAuth) return boot.config;
  throw StateError('الإعداد غير جاهز بعد.');
});

/// الساعة المصحَّحة — كلّ عدّاد في التطبيق يقرأ منها.
final clockProvider = Provider<ServerClock>(
  (ref) => ref.watch(configProvider).clock,
);

final currentUserProvider = Provider<AppUser?>((ref) {
  final boot = ref.watch(bootControllerProvider);
  return boot is BootReady ? boot.user : null;
});

/// لقطة الرحلة القائمة كما جاءت من الإقلاع — نقطة البدء لا مصدر دائم.
final bootSnapshotProvider = Provider<ActiveRideSnapshot?>((ref) {
  final boot = ref.watch(bootControllerProvider);
  return boot is BootReady ? boot.snapshot : null;
});
