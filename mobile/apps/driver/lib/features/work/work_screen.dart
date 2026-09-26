/// شاشة العمل — الحضور، والطلبات المتاحة، وبطاقة تقديم العرض.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import '../presence/presence_bar.dart';
import '../run/run_screen.dart';
import '../presence/presence_controller.dart';
import 'offer_sheet.dart';
import 'work_controller.dart';

class WorkScreen extends ConsumerWidget {
  const WorkScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final work = ref.watch(workControllerProvider);
    final presence = ref.watch(presenceControllerProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(strings.appNameDriver),
        actions: [
          // نشر السفريات يتبع الخدمة في كتالوج المشغّل.
          if (ref.watch(configProvider).serviceActive('published_trips'))
            IconButton(
              icon: const Icon(Icons.add_road_rounded),
              tooltip: strings.publishTitle,
              onPressed: () => context.push('/publish'),
            ),
          IconButton(
            icon: const Icon(Icons.account_balance_wallet_outlined),
            tooltip: strings.balanceTitle,
            onPressed: () => context.push('/balance'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(workControllerProvider.notifier).refreshCandidates(),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const PresenceBar(),
            const SizedBox(height: 18),
            if (work.ride?.scheduledAt != null && work.trip != null) ...[
              _BookingCard(
                ride: work.ride!,
                onOpen: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => const RunScreen()),
                ),
              ),
              const SizedBox(height: 18),
            ],

            Text(strings.workCandidates, style: theme.textTheme.titleMedium),
            const SizedBox(height: 10),

            if (!presence.isMatchable)
              _Hint(
                text: presence.isOnline
                    ? strings.driverOnlineNoHeartbeatHint
                    : strings.workNoCandidatesHint,
              )
            else if (work.candidates.isEmpty)
              _Hint(text: strings.workNoCandidatesHint)
            else
              for (final ride in work.candidates) ...[
                CandidateCard(
                  ride: ride,
                  onOffer: () => showOfferSheet(context, ride),
                ),
                const SizedBox(height: 8),
              ],
          ],
        ),
      ),
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: theme.textTheme.bodySmall,
      ),
    );
  }
}

class CandidateCard extends ConsumerWidget {
  const CandidateCard({super.key, required this.ride, required this.onOffer});

  final RideRequest ride;
  final VoidCallback onOffer;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final clock = ref.watch(clockProvider);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        strings.passengers(ride.passengerCount),
                        style: theme.textTheme.titleMedium,
                      ),
                      // السائق يقرّر وهو يعرف: زبونٌ ألغى مرارًا بعد قبولٍ
                      // قد يكلّفه مشوارًا فارغًا.
                      if (ride.customerLateCancels > 0) ...[
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.error.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            strings.lateCancelBadge(ride.customerLateCancels),
                            style: theme.textTheme.labelSmall
                                ?.copyWith(color: theme.colorScheme.error),
                          ),
                        ),
                      ],
                      // كم يبعد الالتقاء عنّي؟ السؤال الأوّل لأيّ سائق قبل
                      // أن يعرض — والخادم يعرف المسار لا موقع السائق الآن.
                      if (_pickupAway(ref, ride) case final meters?) ...[
                        const SizedBox(height: 2),
                        Text(
                          strings.workPickupAway(meters >= 1000
                              ? strings.unitKm((meters / 1000).toStringAsFixed(1))
                              : strings.unitMeters('${(meters / 10).round() * 10}')),
                          style: SoumTheme.tabular(theme.textTheme.bodySmall!)
                              .copyWith(fontWeight: FontWeight.w600),
                        ),
                      ],
                      const SizedBox(height: 2),
                      Text(
                        [
                          if (ride.routeDistanceKm != null)
                            strings.unitKm(ride.routeDistanceKm!),
                          if (ride.routeDurationMinutes != null)
                            strings.unitMinutes(ride.routeDurationMinutes!),
                        ].join(' · '),
                        style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                      ),
                    ],
                  ),
                ),
                // العدّاد على مهلة الطلب لا على مهلة العرض: الطلب قد
                // ينقضي قبل أن يُرسل السائق عرضه.
                SoumCountdown(
                  deadline: ride.expiresAt,
                  clock: clock,
                  builder: (context, seconds) => Text(
                    // «9:58» لا «598 ثانية»: مهلة البحث دقائق لا ثوانٍ.
                    formatClock(seconds),
                    style: SoumTheme.tabular(
                      theme.textTheme.labelMedium!.copyWith(
                        color: seconds < 30
                            ? theme.colorScheme.error
                            : theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // الزبون عرض سعره: هو الرقم الأهمّ في البطاقة، لا
                      // تسعيرة المنصّة — السائق يقبله أو يعرض أعلى.
                      if (ride.customerProposedFare != null) ...[
                        Text(
                          strings.workCustomerPriceLabel,
                          style: theme.textTheme.labelSmall,
                        ),
                        MoneyText(
                          ride.customerProposedFare!,
                          style: theme.textTheme.titleLarge,
                        ),
                      ] else ...[
                        Text(strings.fareGross, style: theme.textTheme.labelSmall),
                        MoneyText(
                          ride.fare.grossFare,
                          style: theme.textTheme.titleLarge,
                        ),
                      ],
                      // الممرّ يُعرض قبل الإدخال: السائق يعرف الحدّ قبل
                      // أن يرسل سعرًا سيُرفض.
                      if (ride.customerProposedFare == null &&
                          ride.fare.fareFloor != null &&
                          ride.fare.fareCap != null)
                        Text(
                          strings.workFareRange(
                            ride.fare.fareFloor!.format(),
                            ride.fare.fareCap!.format(),
                          ),
                          style: SoumTheme.tabular(theme.textTheme.labelSmall!),
                        ),
                    ],
                  ),
                ),
                FilledButton(
                  onPressed: onOffer,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(110, 42),
                  ),
                  child: Text(strings.workOfferTitle),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// موعدٌ محجوز عند السائق: متى، وكم يقبض، وزرٌّ يفتح شاشة التنفيذ حين يحين.
class _BookingCard extends StatelessWidget {
  const _BookingCard({required this.ride, required this.onOpen});

  final RideRequest ride;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).toString();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(Icons.event_available_rounded,
                color: theme.colorScheme.tertiary, size: 28),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    strings.driverBookingTitle(
                      DateFormat(strings.scheduleFormat, locale)
                          .format(ride.scheduledAt!),
                    ),
                    style: theme.textTheme.titleMedium,
                  ),
                  Row(
                    children: [
                      Text(strings.fareDriverNet,
                          style: theme.textTheme.bodySmall),
                      const SizedBox(width: 6),
                      MoneyText(ride.fare.driverNet,
                          style: theme.textTheme.titleSmall),
                    ],
                  ),
                ],
              ),
            ),
            // زرٌّ بعرضٍ محدود: داخل صفٍّ يأخذ FilledButton ارتفاعًا غير
            // محدود ويمدّ البطاقة على الشاشة كلّها (قِيس على الهاتف).
            SizedBox(
              width: 84,
              height: 44,
              child: FilledButton.tonal(
                onPressed: onOpen,
                style: FilledButton.styleFrom(
                  minimumSize: Size.zero,
                  padding: EdgeInsets.zero,
                ),
                child: Text(strings.driverBookingOpen),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// المسافة من موقع السائق إلى نقطة الالتقاء بالمتر — null حين يغيب أحدهما.
double? _pickupAway(WidgetRef ref, RideRequest ride) {
  final me = ref.watch(presenceControllerProvider).lastPosition;
  final pickup = ride.pickup;
  if (me == null || pickup == null) return null;
  return distanceMeters(me, pickup);
}
