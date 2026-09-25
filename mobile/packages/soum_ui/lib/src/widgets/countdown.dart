/// عدّاد مبنيّ على ساعة الخادم.
///
/// كلّ عدّاد في هذا التطبيق يمرّ من هنا. السبب أنّ البديل — `Timer` في كلّ
/// شاشة يطرح من `DateTime.now()` — يخطئ بفارق انحراف ساعة الجهاز، وهو
/// قاتل عند مهلة دعوة طولها عشرون ثانية.
///
/// وتحديث كلّ ثانية لا أسرع: عدّاد يُعاد بناؤه ستّين مرّة في الثانية على
/// شاشة فيها خريطة حيّة يستهلك بطارية بلا أن يضيف معلومة — الرقم لا يتغيّر
/// إلّا مرّة في الثانية أصلًا.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:soum_core/soum_core.dart';

import '../theme/soum_theme.dart';

class SoumCountdown extends StatefulWidget {
  const SoumCountdown({
    super.key,
    required this.deadline,
    required this.clock,
    required this.builder,
    this.onExpired,
  });

  /// من الخادم — `expires_at`.
  final DateTime? deadline;

  final ServerClock clock;

  final Widget Function(BuildContext, int secondsRemaining) builder;

  /// تُنادى مرّة واحدة عند بلوغ الصفر.
  final VoidCallback? onExpired;

  @override
  State<SoumCountdown> createState() => _SoumCountdownState();
}

class _SoumCountdownState extends State<SoumCountdown> {
  Timer? _timer;
  late int _remaining;
  bool _notified = false;

  @override
  void initState() {
    super.initState();
    _remaining = widget.clock.secondsUntil(widget.deadline);
    _start();
  }

  @override
  void didUpdateWidget(SoumCountdown old) {
    super.didUpdateWidget(old);
    if (old.deadline != widget.deadline) {
      _notified = false;
      _remaining = widget.clock.secondsUntil(widget.deadline);
      _start();
    }
  }

  void _start() {
    _timer?.cancel();
    if (_remaining <= 0) {
      _fireExpired();
      return;
    }
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      final next = widget.clock.secondsUntil(widget.deadline);
      setState(() => _remaining = next);
      if (next <= 0) {
        _timer?.cancel();
        _fireExpired();
      }
    });
  }

  void _fireExpired() {
    if (_notified) return;
    _notified = true;
    // بعد الإطار: المستدعي غالبًا يغيّر حالةً أعلى في الشجرة، وفعلُ ذلك
    // أثناء البناء يرمي.
    WidgetsBinding.instance.addPostFrameCallback((_) => widget.onExpired?.call());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(context, _remaining);
}

/// حلقة تتناقص — لبطاقة العرض وشاشة الدعوة.
class CountdownRing extends StatelessWidget {
  const CountdownRing({
    super.key,
    required this.secondsRemaining,
    required this.totalSeconds,
    this.size = 44,
  });

  final int secondsRemaining;
  final int totalSeconds;
  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final progress =
        totalSeconds <= 0 ? 0.0 : (secondsRemaining / totalSeconds).clamp(0.0, 1.0);

    // اللون يتبدّل عند الخُمس الأخير: المهلة قد تكون عشرين ثانية، والرقم
    // وحده لا يُنبّه من ينظر إلى الطريق لا إلى الشاشة.
    final isUrgent = progress <= 0.2;
    final color = isUrgent ? scheme.error : scheme.primary;

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox.expand(
            child: CircularProgressIndicator(
              value: progress,
              strokeWidth: 3,
              backgroundColor: scheme.outlineVariant,
              valueColor: AlwaysStoppedAnimation(color),
            ),
          ),
          Text(
            '$secondsRemaining',
            textDirection: TextDirection.ltr,
            style: SoumTheme.tabular(
              Theme.of(context).textTheme.labelLarge!.copyWith(
                    // الرقم بالحبر لا بلون الحلقة: الأصفر رقمًا على سطح
                    // فاتح لا يُقرأ، والحلقة وحدها تكفي لحمل اللون.
                    color: isUrgent ? color : scheme.onSurface,
                    fontSize: size * 0.34,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
