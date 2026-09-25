/// القشرة — الشاشة تتبع `stage` ولا شيء غيرها.
///
/// §2.2 و§12.3: النداء الواحد يقرّر الشاشة، والأحداث الحيّة تغيّرها بعده.
/// لا `Navigator.push` هنا: التنقّل بالدفع يعني شاشتين متراكمتين حين تصل
/// حالة لا تتوقّعهما — إلغاءٌ من الإدارة مثلًا وسط رحلة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import 'features/auction/auction_screen.dart';
import 'features/finish/finish_screen.dart';
import 'features/home/home_screen.dart';
import 'features/ride/ride_controller.dart';
import 'features/ride/ride_state.dart';
import 'features/trip/trip_screen.dart';

class CustomerShell extends ConsumerWidget {
  const CustomerShell({super.key, required this.boot});

  final BootReady boot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final arc = ref.watch(rideControllerProvider);

    // انتقالٌ متحرّك بين المراحل لا قفزة: المستخدم يتابع سيارةً تتحرّك،
    // وتبدّلٌ مفاجئ يجعله يظنّ أنّ التطبيق أُعيد تشغيله.
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 240),
      child: KeyedSubtree(
        key: ValueKey(_screenKey(arc.stage, arc)),
        child: switch (arc.stage) {
          ResumeStage.idle => const HomeScreen(),
          // المجدول ينتظر موعده لا سائقًا الآن: الرئيسية تبقى مفتوحة —
          // يطلب مشوارًا فوريًّا بجانبه — وبطاقة «موعدك» تفتح عروضه (العيب #36).
          ResumeStage.searching ||
          ResumeStage.choosingOffer =>
            arc.ride?.isScheduled == true
                ? const HomeScreen()
                : const AuctionScreen(),
          // حجزُ الغد بسائقٍ مؤكَّد ما زال «موعدًا» لا رحلةً جارية: الرئيسية
          // مع بطاقة الموعد. شاشة الرحلة تُفتح حين يقترب الموعد بساعة أو
          // يتحرّك السائق فعلًا (وصل/بدأ).
          ResumeStage.driverAssigned ||
          ResumeStage.driverArriving when _isFarBooking(arc) =>
            const HomeScreen(),
          ResumeStage.driverAssigned ||
          ResumeStage.driverArriving ||
          ResumeStage.driverArrived ||
          ResumeStage.inProgress =>
            const TripScreen(),
          ResumeStage.awaitingPayment => const FinishScreen(),
          // مرحلة لا يعرفها هذا الإصدار: الخادم قد يضيف واحدة. الرئيسية
          // شاشةٌ صالحة دائمًا، وهي أفضل من شاشة بيضاء.
          ResumeStage.unknown => const HomeScreen(),
        },
      ),
    );
  }

  /// البحث واختيار العرض شاشةٌ واحدة، فلا تُعاد بناؤها بينهما.
  static String _screenKey(ResumeStage stage, RideArc arc) => switch (stage) {
        ResumeStage.searching || ResumeStage.choosingOffer =>
          arc.ride?.isScheduled == true ? 'home' : 'auction',
        ResumeStage.driverAssigned ||
        ResumeStage.driverArriving when _isFarBooking(arc) => 'home',
        ResumeStage.driverAssigned ||
        ResumeStage.driverArriving ||
        ResumeStage.driverArrived ||
        ResumeStage.inProgress =>
          'trip',
        ResumeStage.awaitingPayment => 'finish',
        _ => 'home',
      };
}

/// موعدٌ مؤكَّد بعيدٌ عن الآن بأكثر من ساعة ولم تبدأ رحلته.
bool _isFarBooking(RideArc arc) {
  final when = arc.ride?.scheduledAt;
  if (when == null) return false;
  // الخادم يُنشئ الرحلة لحظة اختيار العرض ولو كان الموعد غدًا؛ ما دام
  // السائق لم يصل ولم يبدأ فهي حجزٌ لا رحلة جارية.
  final status = arc.trip?.status;
  final moving = status == TripStatus.driverArrived ||
      status == TripStatus.inProgress;
  if (moving) return false;
  return when.difference(DateTime.now()) > const Duration(hours: 1);
}
