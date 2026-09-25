/// شاشتا المصادقة — مشتركتان بين التطبيقين.
///
/// الخادم لا يفرّق بين زبون وسائق في تسجيل الدخول: الدور يأتي مع المستخدم
/// بعد التحقّق، وتحويل حساب إلى سائق نقطةٌ منفصلة. فنسختان من هاتين
/// الشاشتين تكراران لا فرقان.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';

import '../l10n/generated/soum_strings.dart';
import '../theme/soum_theme.dart';
import '../widgets/brand_logo.dart';
import '../widgets/countdown.dart';
import 'auth_controller.dart';
import 'phone.dart';

class AuthFlow extends ConsumerWidget {
  const AuthFlow({super.key, required this.appName});

  final String appName;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);

    final onCodeStep = switch (state) {
      AuthCodeSent() || AuthVerifying() => true,
      AuthFailed(:final previous) =>
        previous is AuthCodeSent || previous is AuthVerifying,
      _ => false,
    };

    return Scaffold(
      body: SafeArea(
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 220),
          child: onCodeStep
              ? const _CodeStep(key: ValueKey('code'))
              : _PhoneStep(key: const ValueKey('phone'), appName: appName),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------
// الخطوة الأولى — الهاتف
// ---------------------------------------------------------------

class _PhoneStep extends ConsumerStatefulWidget {
  const _PhoneStep({super.key, required this.appName});

  final String appName;

  @override
  ConsumerState<_PhoneStep> createState() => _PhoneStepState();
}

class _PhoneStepState extends ConsumerState<_PhoneStep> {
  final _controller = TextEditingController();
  bool _touched = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _isValid => SyrianPhone.isValid(_controller.text);

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final state = ref.watch(authControllerProvider);
    final controller = ref.read(authControllerProvider.notifier);

    final isSending = state is AuthSending;
    final failure = state is AuthFailed ? state.failure : null;
    final cooldown = controller.otpCooldown;

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 40),
          const Align(
            alignment: AlignmentDirectional.centerStart,
            child: BrandLogo(size: 104, radius: 24),
          ),
          const SizedBox(height: 18),
          Text(widget.appName, style: theme.textTheme.displaySmall),
          const SizedBox(height: 28),
          Text(strings.authPhoneTitle, style: theme.textTheme.titleLarge),
          const SizedBox(height: 6),
          Text(
            strings.authPhoneSubtitle,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 24),
          TextField(
            controller: _controller,
            keyboardType: TextInputType.phone,
            autofillHints: const [AutofillHints.telephoneNumber],
            // الرقم يُكتب من اليسار حتّى في واجهة عربية: خلطُ اتجاه
            // الأرقام مع اتجاه النصّ يضع رمز البلد في الطرف الخطأ.
            textDirection: TextDirection.ltr,
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'[\d+ ]')),
              LengthLimitingTextInputFormatter(16),
            ],
            decoration: InputDecoration(
              labelText: strings.authPhoneLabel,
              hintText: strings.authPhoneHint,
              prefixText: '${SyrianPhone.countryCode} ',
              prefixStyle: SoumTheme.tabular(theme.textTheme.bodyLarge!),
              errorText:
                  _touched && !_isValid ? strings.authPhoneInvalid : null,
            ),
            style: SoumTheme.tabular(theme.textTheme.bodyLarge!),
            onChanged: (_) => setState(() => _touched = true),
            onSubmitted: (_) => _submit(),
          ),
          const SizedBox(height: 20),
          if (cooldown != null)
            _ThrottleNotice(seconds: cooldown.inSeconds)
          else
            FilledButton(
              onPressed: _isValid && !isSending ? _submit : null,
              child: isSending
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    )
                  : Text(strings.authSendCode),
            ),
          if (failure != null && !failure.isThrottled) ...[
            const SizedBox(height: 14),
            _InlineError(failure: failure),
          ],
        ],
      ),
    );
  }

  void _submit() {
    setState(() => _touched = true);
    if (!_isValid) return;
    FocusScope.of(context).unfocus();
    ref.read(authControllerProvider.notifier).requestCode(_controller.text);
  }
}

// ---------------------------------------------------------------
// الخطوة الثانية — الرمز
// ---------------------------------------------------------------

class _CodeStep extends ConsumerStatefulWidget {
  const _CodeStep({super.key});

  @override
  ConsumerState<_CodeStep> createState() => _CodeStepState();
}

class _CodeStepState extends ConsumerState<_CodeStep> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final state = ref.watch(authControllerProvider);
    final controller = ref.read(authControllerProvider.notifier);

    final sent = switch (state) {
      final AuthCodeSent s => s,
      AuthFailed(previous: final AuthCodeSent s) => s,
      _ => null,
    };
    final isVerifying = state is AuthVerifying;
    final failure = state is AuthFailed ? state.failure : null;

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 56),
          Text(strings.authCodeTitle, style: theme.textTheme.headlineSmall),
          const SizedBox(height: 6),
          Text(
            strings.authCodeSubtitle(
              SyrianPhone.pretty(sent?.phone ?? ''),
            ),
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),

          // في التطوير يعود الرمز في الجسم نفسه، فيُختبر التدفّق بلا
          // اشتراك رسائل. الحقل يختفي تمامًا في الإنتاج، فلا يُبنى عليه
          // منطق — هذا عرضٌ فقط.
          if (sent?.developmentCode != null) ...[
            const SizedBox(height: 14),
            _DevelopmentCode(code: sent!.developmentCode!),
          ],

          const SizedBox(height: 22),
          TextField(
            controller: _controller,
            autofocus: true,
            keyboardType: TextInputType.number,
            textAlign: TextAlign.center,
            textDirection: TextDirection.ltr,
            autofillHints: const [AutofillHints.oneTimeCode],
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(6),
            ],
            style: SoumTheme.tabular(
              theme.textTheme.displaySmall!.copyWith(letterSpacing: 8),
            ),
            decoration: InputDecoration(
              hintText: '••••••',
              counterText: '',
              errorText: failure != null && failure.isValidation
                  ? failure.detail
                  : null,
            ),
            onChanged: (value) {
              // الأرقام في هذا الخادم ستّة. التحقّق التلقائي عند اكتمالها
              // يوفّر ضغطة، ولا يُطلق نداءً على رمز ناقص.
              if (value.length == 6 && !isVerifying) _submit();
            },
          ),

          if (sent?.expiresAt != null) ...[
            const SizedBox(height: 12),
            SoumCountdown(
              deadline: sent!.expiresAt,
              clock: ServerClock.synced,
              builder: (context, seconds) => Text(
                seconds > 0
                    ? strings.authCodeExpiresIn(seconds)
                    : strings.authResend,
                textAlign: TextAlign.center,
                style: theme.textTheme.labelMedium,
              ),
            ),
          ],

          const SizedBox(height: 20),
          FilledButton(
            onPressed:
                _controller.text.length >= 4 && !isVerifying ? _submit : null,
            child: isVerifying
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2.2),
                  )
                : Text(strings.authVerify),
          ),

          const SizedBox(height: 8),
          _ResendRow(controller: controller),

          if (failure != null && !failure.isValidation) ...[
            const SizedBox(height: 14),
            _InlineError(failure: failure),
          ],
        ],
      ),
    );
  }

  void _submit() {
    FocusScope.of(context).unfocus();
    ref.read(authControllerProvider.notifier).verify(_controller.text);
  }
}

class _ResendRow extends StatelessWidget {
  const _ResendRow({required this.controller});

  final AuthController controller;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final cooldown = controller.otpCooldown;

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        TextButton(
          onPressed: controller.restart,
          child: Text(strings.authChangePhone),
        ),
        if (cooldown != null)
          Text(
            strings.authResendIn(cooldown.inSeconds),
            style: Theme.of(context).textTheme.labelMedium,
          )
        else
          TextButton(
            onPressed: controller.resend,
            child: Text(strings.authResend),
          ),
      ],
    );
  }
}

class _DevelopmentCode extends StatelessWidget {
  const _DevelopmentCode({required this.code});

  final String code;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final scheme = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: scheme.secondary.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.secondary.withValues(alpha: 0.3)),
      ),
      child: Text(
        strings.authDevelopmentCode(code),
        textAlign: TextAlign.center,
        style: Theme.of(context)
            .textTheme
            .labelMedium
            ?.copyWith(color: scheme.secondary),
      ),
    );
  }
}

class _ThrottleNotice extends StatelessWidget {
  const _ThrottleNotice({required this.seconds});

  final int seconds;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);

    // العدّاد يُبنى من المدّة التي أعطاها الخادم، ولا نداء يخرج قبل
    // انقضائها — النداء داخل النافذة يجدّدها فيحبس المستخدم.
    return SoumCountdown(
      deadline: DateTime.now().add(Duration(seconds: seconds)),
      clock: ServerClock.synced,
      builder: (context, left) => FilledButton(
        onPressed: null,
        child: Text(strings.authThrottled(left)),
      ),
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError({required this.failure});

  final ApiException failure;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.errorContainer.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline_rounded, size: 18, color: scheme.error),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              // النصّ من الخادم لا من التطبيق: هو ما يشرح السبب فعلًا.
              failure.detail,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.onSurface),
            ),
          ),
        ],
      ),
    );
  }
}
