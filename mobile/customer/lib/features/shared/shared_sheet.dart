/// المشاركة — الانضمام إلى رحلة قائمة أو مجدولة.
///
/// تُفتح من شاشة البحث حين يكون النمط `shared`. والفرق بين القائمتين
/// ليس شكليًّا:
///
///   **القائمة** — سيارةٌ تسير الآن وفيها مقعد. التوافق يقيس كم يضيف
///   انضمامُك على طريق الركّاب الحاليين، والمهلة قصيرة.
///
///   **المجدولة** — رحلة في المستقبل ضمن نافذة ستّين دقيقة. لا عجلة،
///   والفلترة بالنافذة وأنصاف الأقطار يجريها الخادم.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';


Future<void> showSharedSheet(BuildContext context, int rideId) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => _SharedSheet(rideId: rideId),
  );
}

class _SharedSheet extends ConsumerStatefulWidget {
  const _SharedSheet({required this.rideId});

  final int rideId;

  @override
  ConsumerState<_SharedSheet> createState() => _SharedSheetState();
}

class _SharedSheetState extends ConsumerState<_SharedSheet> {
  List<SharedJoinOffer> _instant = const [];
  List<ScheduledSharedTrip> _scheduled = const [];
  bool _loading = true;
  ApiException? _failure;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final soum = ref.read(soumProvider);

    try {
      // القائمتان معًا: الزبون لا يعرف الفرق ولا يهمّه — يريد مقعدًا.
      final instant = await soum.sharing.sharedOffers(widget.rideId);
      final scheduled =
          await soum.sharing.scheduledSharedTrips(widget.rideId);

      if (!mounted) return;
      setState(() {
        _instant = instant;
        _scheduled = scheduled;
        _failure = null;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _failure = error;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * 0.8,
      ),
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: theme.colorScheme.outlineVariant,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 14),
            Text(strings.sharedTitle, style: theme.textTheme.titleLarge),
            const SizedBox(height: 12),

            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 28),
                child: Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
              )
            else if (_failure != null)
              ApiErrorView(failure: _failure!, compact: true, onRetry: _load)
            else if (_instant.isEmpty && _scheduled.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 28),
                child: Center(
                  child: Text(strings.sharedNone,
                      style: theme.textTheme.bodyMedium),
                ),
              )
            else
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final offer in _instant) ...[
                      _InstantCard(offer: offer, onJoin: () => _join(offer)),
                      const SizedBox(height: 8),
                    ],
                    for (final trip in _scheduled) ...[
                      _ScheduledCard(trip: trip, onJoin: () => _joinScheduled(trip)),
                      const SizedBox(height: 8),
                    ],
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _join(SharedJoinOffer offer) async {
    await _attempt(() =>
        ref.read(soumProvider).sharing.acceptSharedOffer(offer.id));
  }

  Future<void> _joinScheduled(ScheduledSharedTrip trip) async {
    await _attempt(() => ref.read(soumProvider).sharing.joinScheduledSharedTrip(
          rideId: widget.rideId,
          tripId: trip.id,
        ));
  }

  Future<void> _attempt(Future<void> Function() action) async {
    try {
      await action();
      if (!mounted) return;

      final strings = SoumStrings.of(context);
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(strings.sharedJoined)));

      // الحالة تُقرأ من الخادم: الانضمام يُنشئ رحلة، وشكلها من عنده.
      await ref.read(bootControllerProvider.notifier).refreshActiveRide();
    } on ApiException catch (error) {
      if (!mounted) return;

      final strings = SoumStrings.of(context);
      // السباق نفسه الذي في المزاد: راكبٌ آخر شغل المقعد بين العرض
      // والقبول. رسالةٌ لطيفة وقائمة محدَّثة لا شاشة خطأ.
      final message =
          error.statusCode == 409 ? strings.sharedFull : error.detail;

      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(message)));
      await _load();
    }
  }
}

class _InstantCard extends StatelessWidget {
  const _InstantCard({required this.offer, required this.onJoin});

  final SharedJoinOffer offer;
  final VoidCallback onJoin;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final summary = offer.genderSummary;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.groups_rounded, color: theme.colorScheme.secondary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(offer.vehicleLabel, style: theme.textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(
                    strings.sharedCompatibility(offer.compatibilityScore),
                    style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                  ),
                  if (offer.seatsAvailable != null)
                    Text(
                      strings.sharedSeatsLeft(offer.seatsAvailable!),
                      style: theme.textTheme.labelSmall,
                    ),
                  // يُعرض حين يسمح به المشغّل وحده — القرار من الخادم.
                  if (summary != null)
                    Text(
                      strings.sharedOnboard(
                        summary['male'] ?? 0,
                        summary['female'] ?? 0,
                      ),
                      style: theme.textTheme.labelSmall,
                    ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                MoneyText(offer.fareEstimate,
                    style: theme.textTheme.titleMedium),
                const SizedBox(height: 4),
                FilledButton(
                  onPressed: onJoin,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(74, 32),
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                  ),
                  child: Text(strings.sharedJoin),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ScheduledCard extends StatelessWidget {
  const _ScheduledCard({required this.trip, required this.onJoin});

  final ScheduledSharedTrip trip;
  final VoidCallback onJoin;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).toString();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.schedule_rounded, color: theme.colorScheme.tertiary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    trip.title ?? trip.vehicleLabel,
                    style: theme.textTheme.titleMedium,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    strings.catalogDeparts(
                      DateFormat.MMMd(locale).add_jm().format(trip.scheduledAt),
                    ),
                    style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                  ),
                  Text(
                    strings.sharedSeatsLeft(trip.remainingCapacity),
                    style: theme.textTheme.labelSmall,
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (trip.pricePerSeat != null)
                  MoneyText(trip.pricePerSeat!,
                      style: theme.textTheme.titleMedium),
                const SizedBox(height: 4),
                FilledButton(
                  onPressed: trip.hasRoom ? onJoin : null,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(74, 32),
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                  ),
                  child: Text(strings.sharedJoin),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
