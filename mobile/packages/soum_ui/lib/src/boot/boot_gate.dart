/// البوّابة — ترسم ما تقوله حالة الإقلاع، ولا شيء غيرها.
///
/// الشاشة تتبع الحالة لا العكس. هذا هو الفرق العمليّ بين تطبيق يعود
/// المستخدم فيه إلى شاشة التتبّع بعد إغلاق التطبيق، وتطبيقٍ يفتح شاشة
/// «اطلب رحلة» فوق رحلة قائمة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';

import '../auth/auth_screens.dart';
import '../l10n/generated/soum_strings.dart';
import '../widgets/brand_logo.dart';
import '../widgets/error_view.dart';
import 'boot_controller.dart';
import 'boot_state.dart';

class BootGate extends ConsumerWidget {
  const BootGate({
    super.key,
    required this.appName,
    required this.onReady,
  });

  final String appName;

  /// يبني شجرة التطبيق من الحالة الجاهزة. `snapshot.stage` هو ما يقرّر
  /// الشاشة — لا سجلّ الرحلات ولا حساب محلّي.
  final Widget Function(BuildContext, BootReady) onReady;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(bootControllerProvider);

    return switch (state) {
      BootLoading(:final step) => _Splash(appName: appName, step: step),
      BootNeedsAuth() => AuthFlow(appName: appName),
      BootReady() => onReady(context, state),
      BootFailed(:final failure) => _BootError(failure: failure),
    };
  }
}

class _Splash extends StatelessWidget {
  const _Splash({required this.appName, required this.step});

  final String appName;
  final BootStep step;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    final message = switch (step) {
      BootStep.config => strings.bootLoadingConfig,
      BootStep.session => strings.bootLoadingSession,
      BootStep.activeRide => strings.bootRestoringRide,
    };

    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const BrandLogo(),
            const SizedBox(height: 18),
            Text(appName, style: theme.textTheme.headlineMedium),
            const SizedBox(height: 28),
            const SizedBox(
              width: 26,
              height: 26,
              child: CircularProgressIndicator(strokeWidth: 2.4),
            ),
            const SizedBox(height: 16),
            // الرسالة تتبدّل مع الخطوة: «نستعيد جلستك» ثمّ «نعيدك إلى
            // رحلتك». مؤشّرٌ صامت لا يقول شيئًا يجعل ثانيتين تبدوان عطلًا.
            Text(message, style: theme.textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _BootError extends ConsumerWidget {
  const _BootError({required this.failure});

  final ApiException failure;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      body: Center(
        child: ApiErrorView(
          failure: failure,
          onRetry: () => ref.read(bootControllerProvider.notifier).start(),
        ),
      ),
    );
  }
}
