/// قشرة تطبيق السائق.
///
/// ثلاثة مسارات لا واحد، ويقرّرها الخادم لا التطبيق:
///
///   حسابٌ لم يكتمل توثيقه          → شاشة التوثيق
///   سائقٌ جاهز بلا رحلة            → شاشة العمل
///   سائقٌ على رحلة                 → شاشة التنفيذ
///
/// والدعوة الواردة تعلو أيًّا منها: مهلتها عشرون ثانية، وإخفاؤها خلف
/// شاشة أخرى يعني تفويتها.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import 'features/earnings/balance_screen.dart';
import 'features/onboarding/onboarding_controller.dart';
import 'features/onboarding/onboarding_screen.dart';
import 'features/run/run_screen.dart';
import 'features/work/invitation_overlay.dart';
import 'features/work/work_controller.dart';
import 'features/work/work_screen.dart';

class DriverShell extends ConsumerWidget {
  const DriverShell({super.key, required this.boot});

  final BootReady boot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final onboarding = ref.watch(onboardingControllerProvider);
    final work = ref.watch(workControllerProvider);

    // الزبون ألغى (أو الإدارة): الشاشة تعود للقائمة، والرسالة تقول لماذا.
    ref.listen(workControllerProvider.select((w) => w.endNotice), (previous, next) {
      if (next == null || identical(next, previous)) return;
      final strings = SoumStrings.of(context);
      final compensation = next.compensation;
      final message = !next.byCustomer
          ? strings.tripCancelledBy
          : compensation == null
              ? strings.runCustomerCancelled
              : strings.runCustomerCancelledCompensated(compensation.format());
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(
          content: Text(message),
          duration: const Duration(seconds: 6),
        ));
    });

    // الرحلة القائمة تسبق كلّ شيء: سائقٌ توثيقه انتهت صلاحيته وسط رحلة
    // يجب أن يُكملها لا أن يُرمى إلى شاشة رفع وثائق.
    final Widget body;
    if (work.hasRunningTrip && !_isFarBooking(work)) {
      body = const RunScreen();
    } else if (work.stage == ResumeStage.awaitingPayment &&
        work.payment != null) {
      body = _CollectScreen(payment: work.payment!);
    } else if (onboarding.step != OnboardingStep.ready) {
      body = const OnboardingScreen();
    } else {
      body = const WorkScreen();
    }

    return Stack(
      children: [
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 220),
          child: KeyedSubtree(
            key: ValueKey(body.runtimeType),
            child: body,
          ),
        ),
        const InvitationOverlay(),
      ],
    );
  }
}

class _CollectScreen extends ConsumerWidget {
  const _CollectScreen({required this.payment});

  final Payment payment;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final work = ref.watch(workControllerProvider);

    return Scaffold(
      appBar: AppBar(title: Text(strings.collectTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          CollectCard(
            payment: payment,
            isBusy: work.isBusy,
            onCollect: ref.read(workControllerProvider.notifier).collectCash,
          ),
          if (work.failure != null) ...[
            const SizedBox(height: 16),
            ApiErrorView(failure: work.failure!, compact: true),
          ],
        ],
      ),
    );
  }
}

/// حجزُ الغد: رحلةٌ أُنشئت الآن بموعدٍ بعيد ولم يتحرّك السائق إليها بعد.
/// تُعرض بطاقةً في شاشة العمل لا شاشةَ تنفيذٍ تحبس السائق يومًا كاملًا.
bool _isFarBooking(WorkState work) {
  final when = work.ride?.scheduledAt;
  final status = work.trip?.status;
  if (when == null || status == null) return false;
  final moving =
      status == TripStatus.driverArrived || status == TripStatus.inProgress;
  if (moving) return false;
  return when.difference(DateTime.now()) > const Duration(hours: 1);
}
