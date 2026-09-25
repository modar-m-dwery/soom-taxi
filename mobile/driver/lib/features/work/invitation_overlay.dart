/// الدعوة الواردة — شاشة تعلو كلّ شيء.
///
/// المهلة عشرون ثانية افتراضًا. إخفاء الدعوة في زاوية شاشة يجعل السائق
/// يفوّتها وهو ينظر إلى الطريق، فتُعرض فوق كلّ شيء وبعدّاد كبير.
///
/// و§5.1 من جهة الزبون: رفضُ السائق يُفعّل تهدئة ستّين ثانية عند الزبون
/// فتُخفى سيارته مؤقّتًا. الرفض هنا فعلٌ له أثر عند الطرف الآخر، لا مجرّد
/// إغلاق نافذة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import 'work_controller.dart';

class InvitationOverlay extends ConsumerWidget {
  const InvitationOverlay({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final clock = ref.watch(clockProvider);
    final work = ref.watch(workControllerProvider);
    final controller = ref.read(workControllerProvider.notifier);

    final invitation = work.invitation;
    if (invitation == null || !invitation.isPending) {
      return const SizedBox.shrink();
    }

    return Material(
      color: Colors.black.withValues(alpha: 0.55),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(22),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    strings.invitationIncoming,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.titleLarge,
                  ),
                  const SizedBox(height: 18),

                  Center(
                    child: SoumCountdown(
                      deadline: invitation.expiresAt,
                      clock: clock,
                      // الانقضاء يُخفي البطاقة من تلقائه: بطاقةٌ باقية
                      // بعد انتهاء المهلة تُغري بضغطة ترتدّ بـ400.
                      onExpired: () => controller.rejectInvitation(),
                      builder: (context, seconds) => CountdownRing(
                        secondsRemaining: seconds,
                        totalSeconds: invitation.ttlSeconds,
                        size: 84,
                      ),
                    ),
                  ),

                  const SizedBox(height: 18),
                  Row(
                    children: [
                      Text(strings.fareDriverNet,
                          style: theme.textTheme.bodyMedium),
                      const Spacer(),
                      MoneyText(
                        invitation.quotedFare,
                        style: theme.textTheme.headlineSmall,
                      ),
                    ],
                  ),

                  if (invitation.approximateDistanceM != null) ...[
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Text(strings.runToPickup,
                            style: theme.textTheme.bodySmall),
                        const Spacer(),
                        Text(
                          strings.inviteDistance(
                            invitation.approximateDistanceM!,
                          ),
                          style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                        ),
                      ],
                    ),
                  ],

                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: work.isBusy ? null : controller.acceptInvitation,
                    child: Text(strings.invitationAccept),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed:
                        work.isBusy ? null : () => controller.rejectInvitation(),
                    child: Text(strings.invitationReject),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
