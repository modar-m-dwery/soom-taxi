import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';

import '../boot/boot_controller.dart';
import 'phone.dart';

sealed class AuthState {
  const AuthState();
}

class AuthIdle extends AuthState {
  const AuthIdle();
}

class AuthSending extends AuthState {
  const AuthSending();
}

/// رمزٌ أُرسل — ننتقل إلى شاشة التحقّق.
class AuthCodeSent extends AuthState {
  const AuthCodeSent({
    required this.phone,
    required this.expiresAt,
    this.developmentCode,
  });

  final String phone;
  final DateTime? expiresAt;

  /// في وضع التطوير وحده. يختفي تمامًا حين `DEBUG=False`.
  final String? developmentCode;
}

class AuthVerifying extends AuthState {
  const AuthVerifying(this.phone);
  final String phone;
}

class AuthSucceeded extends AuthState {
  const AuthSucceeded(this.user);
  final AppUser user;
}

class AuthFailed extends AuthState {
  const AuthFailed(this.failure, this.previous);
  final ApiException failure;

  /// الحالة قبل الفشل — حتّى تبقى شاشة التحقّق قائمة عند رمز خاطئ بدل
  /// أن يُرمى المستخدم إلى شاشة الهاتف فيعيد كلّ شيء.
  final AuthState previous;
}

final authControllerProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);

class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() => const AuthIdle();

  Soum get _soum => ref.read(soumProvider);

  /// المدّة المتبقّية على حدّ طلب الرمز — لعدّاد مرئيّ بلا نداء.
  Duration? get otpCooldown =>
      _soum.client.throttle.remainingFor('/auth/request-otp/');

  Future<void> requestCode(String rawPhone) async {
    final phone = SyrianPhone.normalize(rawPhone);
    if (phone == null) return;

    final previous = state;
    state = const AuthSending();

    try {
      final challenge = await _soum.auth.requestOtp(phone);
      state = AuthCodeSent(
        phone: phone,
        expiresAt: challenge.expiresAt,
        developmentCode: challenge.developmentCode,
      );
    } on ApiException catch (error) {
      state = AuthFailed(error, previous);
    }
  }

  Future<void> verify(String code) async {
    final current = state;
    final phone = switch (current) {
      AuthCodeSent(:final phone) => phone,
      AuthVerifying(:final phone) => phone,
      AuthFailed(previous: AuthCodeSent(:final phone)) => phone,
      _ => null,
    };
    if (phone == null) return;

    state = AuthVerifying(phone);

    try {
      final user = await _soum.auth.verifyOtp(phone, code);
      state = AuthSucceeded(user);

      // الإقلاع يُعاد كاملًا: الإعداد قد يتغيّر بتغيّر المستخدم، و
      // /me/active-ride/ هو ما يقرّر الشاشة التالية.
      await ref.read(bootControllerProvider.notifier).resumeAfterLogin();
    } on ApiException catch (error) {
      state = AuthFailed(error, current);
    }
  }

  /// العودة إلى شاشة الهاتف.
  void restart() => state = const AuthIdle();

  /// إعادة الإرسال — تمرّ بحارس الحدود نفسه، فلا تُحتسب محاولة إن كانت
  /// النافذة ما زالت مفتوحة.
  Future<void> resend() async {
    final current = state;
    final phone = switch (current) {
      AuthCodeSent(:final phone) => phone,
      AuthFailed(previous: AuthCodeSent(:final phone)) => phone,
      _ => null,
    };
    if (phone != null) await requestCode(phone);
  }
}
