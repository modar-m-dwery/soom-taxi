/// شريط الحضور — يقول الحقيقة لا الظاهر.
///
/// الفرق بين «متّصل» و«تعمل الآن» ليس تجميلًا في النصّ: الأوّل يعني أنّ
/// الخادم قَبِل `go-online`، والثاني يعني أنّ السائق يظهر فعلًا في
/// المطابقة. وبينهما نبضةُ موقع.
///
/// سائقٌ يرى «متّصل» ولا يصله طلب طوال ساعة ولا يعرف أنّ نبضه لا يصل
/// يتّهم المنصّة. عرضُ الفرق يجعل المشكلة مرئيّة في ثانية.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_ui/soum_ui.dart';

import 'presence_controller.dart';
import 'presence_state.dart';

class PresenceBar extends ConsumerWidget {
  const PresenceBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final presence = ref.watch(presenceControllerProvider);
    final controller = ref.read(presenceControllerProvider.notifier);

    final (label, hint, color) = switch (presence.stage) {
      PresenceStage.offline => (
          strings.driverOffline,
          '',
          theme.colorScheme.outline,
        ),
      PresenceStage.connecting => (
          strings.driverConnecting,
          '',
          theme.colorScheme.outline,
        ),
      PresenceStage.onlineNoHeartbeat => (
          strings.driverOnlineNoHeartbeat,
          strings.driverOnlineNoHeartbeatHint,
          theme.colorScheme.tertiary,
        ),
      PresenceStage.matchable => (
          strings.driverMatchable,
          strings.driverMatchableHint,
          theme.colorScheme.secondary,
        ),
      PresenceStage.stale => (
          strings.driverStale,
          strings.driverStaleHint,
          theme.colorScheme.error,
        ),
    };

    // بطاقة الحضور هي «لوحة القيادة» للسائق: حين يعمل تصير سوداء بنصٍّ
    // أصفر كلوحة التاكسي، وحين يتوقّف تعود سطحًا هادئًا. حالةٌ تُقرأ من
    // بعيد بلا قراءة.
    final on = presence.isOnline;
    final scheme = theme.colorScheme;
    final fg = on ? scheme.primary : scheme.onSurface;
    final fgSoft = on ? scheme.surface.withValues(alpha: 0.75) : null;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
      decoration: BoxDecoration(
        color: on ? scheme.onSurface : scheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: on ? Colors.transparent : scheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: on
                        ? scheme.primary.withValues(alpha: 0.16)
                        : scheme.surfaceContainerHighest,
                  ),
                  child: Icon(
                    on ? Icons.local_taxi_rounded : Icons.power_settings_new_rounded,
                    color: on ? scheme.primary : color,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        style: theme.textTheme.titleLarge?.copyWith(color: fg),
                      ),
                      if (hint.isNotEmpty)
                        Text(
                          hint,
                          style: theme.textTheme.bodySmall?.copyWith(color: fgSoft),
                        ),
                    ],
                  ),
                ),
                Switch(
                  value: presence.isOnline,
                  onChanged: presence.stage == PresenceStage.connecting
                      ? null
                      : (wantsOnline) => wantsOnline
                          ? controller.goOnline()
                          : controller.goOffline(),
                ),
              ],
            ),

            if (presence.blocker != PresenceBlocker.none) ...[
              const SizedBox(height: 12),
              _Blocker(presence: presence),
            ],
          ],
        ),
      ),
    );
  }
}

class _Blocker extends StatelessWidget {
  const _Blocker({required this.presence});

  final PresenceState presence;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    // §12.3: «سائق موقوف أو وثائقه منتهية — اعرض السبب من detail لا
    // رسالة عامّة». نصّ الخادم يقول أيّ وثيقة بالضبط، ورسالةٌ عامّة
    // تجعل السائق يبحث عن المشكلة في كلّ مكان.
    final message = switch (presence.blocker) {
      PresenceBlocker.locationUnavailable => strings.driverLocationNeeded,
      PresenceBlocker.serverRefused =>
        presence.failure?.detail ?? strings.driverNotEligible,
      PresenceBlocker.mockLocation => strings.driverMockLocation,
      PresenceBlocker.none => '',
    };

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline_rounded,
              size: 18, color: theme.colorScheme.error),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: theme.textTheme.bodySmall),
          ),
        ],
      ),
    );
  }
}
