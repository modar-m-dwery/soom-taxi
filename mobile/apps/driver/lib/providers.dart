/// المزوّدات الجذرية لتطبيق السائق.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

export 'package:soum_ui/soum_ui.dart' show bootControllerProvider, soumProvider;

final configProvider = Provider<AppConfig>((ref) {
  final boot = ref.watch(bootControllerProvider);
  if (boot is BootReady) return boot.config;
  if (boot is BootNeedsAuth) return boot.config;
  throw StateError('الإعداد غير جاهز بعد.');
});

final clockProvider = Provider<ServerClock>(
  (ref) => ref.watch(configProvider).clock,
);

final currentUserProvider = Provider<AppUser?>((ref) {
  final boot = ref.watch(bootControllerProvider);
  return boot is BootReady ? boot.user : null;
});

final bootSnapshotProvider = Provider<ActiveRideSnapshot?>((ref) {
  final boot = ref.watch(bootControllerProvider);
  return boot is BootReady ? boot.snapshot : null;
});

/// معرّف ملفّ السائق — تُبنى منه غرفة السائق.
///
/// يأتي من `/me/active-ride/` تحت `realtime.driver_room`، ومن
/// `/auth/driver/profile/` حين لا رحلة قائمة. لا يُبنى في التطبيق.
final driverProfileIdProvider = FutureProvider<int?>((ref) async {
  final snapshot = ref.watch(bootSnapshotProvider);

  // المسار الجاهز أوّلًا: `/ws/driver/{id}/` يحمل المعرّف.
  final room = snapshot?.rooms.driverRoom;
  if (room != null) {
    final id = RegExp(r'/ws/driver/(\d+)/').firstMatch(room)?.group(1);
    if (id != null) return int.tryParse(id);
  }

  try {
    final profile = await ref.read(soumProvider).driver.profile();
    return readIntOrNull(profile, 'id');
  } on ApiException {
    // حسابٌ لم يصر سائقًا بعد. ليس خطأً — مسارٌ آخر في الواجهة.
    return null;
  }
});
