/// شاشة التتبّع.
///
/// القاعدة التي تحكمها (§2.1): **لا تحسب الحالة التالية — استقبلها**.
///
/// > الحالة تتغيّر لأسباب لا يراها تطبيقك: مهلة انقضت في Celery، إدارةٌ
/// > ألغت، سائقٌ انقطع اتّصاله. اشترك في غرفة الرحلة واعرض ما يصلك. حساب
/// > الحالة محلّيًّا يعني شاشةً تقول «السائق في الطريق» بينما الرحلة أُلغيت
/// > قبل دقيقة.
///
/// لذلك لا زرّ هنا يغيّر المرحلة محلّيًّا. كلّ ما تعرضه الشاشة مشتقّ من
/// `arc.stage`، وهي مشتقّة من حالات وصلت عبر الغرفة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../call_button.dart';
import '../../providers.dart';
import '../map/vehicle_marker.dart';
import '../ride/ride_controller.dart';

class TripScreen extends ConsumerStatefulWidget {
  const TripScreen({super.key});

  @override
  ConsumerState<TripScreen> createState() => _TripScreenState();
}

class _TripScreenState extends ConsumerState<TripScreen> {
  final _map = OsmMapController();

  @override
  Widget build(BuildContext context) {
    final arc = ref.watch(rideControllerProvider);
    final trip = arc.trip;
    final ride = arc.ride;

    if (trip == null && ride == null) return const SizedBox.shrink();

    final pickup = ride?.pickup;
    final destination = ride?.destination;
    final driver = arc.driverLocation;
    final theme = Theme.of(context);

    return Scaffold(
      body: Stack(
        children: [
          if (pickup != null)
            SoumMap(
              controller: _map,
              initialCamera: MapStart(center: driver ?? pickup, zoom: 15),
              polylines: [
                // الخطّ يُرسم من هندسة المسار حين تكون حقيقية وحدها.
                // خطٌّ مستقيم بدل مسارٍ تعذّر حسابه كذبٌ بصريّ أسوأ من
                // لا شيء — والخادم نفسه يُرسل null في تلك الحالة.
                if (ride?.routeGeometry != null)
                  MapPolyline(
                    points: ride!.routeGeometry!.points,
                    color: theme.colorScheme.primary,
                    width: 4.5,
                  ),
              ],
              markers: [
                pointMarker(
                  id: 'pickup',
                  position: pickup,
                  icon: Icons.trip_origin_rounded,
                  color: theme.colorScheme.secondary,
                ),
                if (destination != null)
                  pointMarker(
                    id: 'destination',
                    position: destination,
                    icon: Icons.place_rounded,
                    color: theme.colorScheme.primary,
                  ),
                // السيارة تنزلق بين نبضات الموقع وتدور مع اتجاه سيرها —
                // الزبون يراها تقترب لا تقفز.
                if (driver != null) driverCarMarker(driver),
              ],
            ),

          Align(
            alignment: Alignment.bottomCenter,
            child: _TripSheet(
              stage: arc.stage,
              trip: trip,
              ride: ride,
              onCancel: () => _cancel(context),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _cancel(BuildContext context) async {
    final strings = SoumStrings.of(context);

    final arc = ref.read(rideControllerProvider);
    final timings = ref.read(configProvider).timings;
    final notice = _cancelNotice(strings, arc.trip, timings);

    // اختيار السبب هو التأكيد نفسه، والرجوع (السحب أو زرّ الرجوع) تراجع.
    // السبب رمزٌ لا نصّ: كاشف الغش يقرأ الرمز، و«السائق طلب منّي أن ألغي»
    // يُحسب على السائق لا على الزبون.
    final reason = await showModalBottomSheet<CancelReason>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (sheetContext) {
        final theme = Theme.of(sheetContext);
        return SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(strings.tripCancelWhy, style: theme.textTheme.titleLarge),
                const SizedBox(height: 6),
                Text(notice, style: theme.textTheme.bodySmall),
                const SizedBox(height: 8),
                for (final option in _reasonOrder)
                  ListTile(
                    title: Text(_reasonLabel(strings, option)),
                    trailing: const Icon(Icons.chevron_left_rounded),
                    onTap: () => Navigator.pop(sheetContext, option),
                  ),
                const SizedBox(height: 4),
                TextButton(
                  onPressed: () => Navigator.pop(sheetContext),
                  child: Text(strings.actionBack),
                ),
              ],
            ),
          ),
        );
      },
    );

    if (reason == null) return;
    await ref
        .read(rideControllerProvider.notifier)
        .cancelRide(reasonCode: reason);
  }
}

/// أسباب السائق أوّلًا: هي الأكثر حين يلغي زبونٌ رحلةً لها سائق.
const _reasonOrder = [
  CancelReason.driverLate,
  CancelReason.driverNotMoving,
  CancelReason.driverAsked,
  CancelReason.wrongPickup,
  CancelReason.foundOther,
  CancelReason.changedMind,
  CancelReason.other,
];

String _reasonLabel(SoumStrings strings, CancelReason reason) =>
    switch (reason) {
      CancelReason.changedMind => strings.riderCancelChangedMind,
      CancelReason.driverLate => strings.riderCancelDriverLate,
      CancelReason.driverNotMoving => strings.riderCancelDriverNotMoving,
      CancelReason.driverAsked => strings.riderCancelDriverAsked,
      CancelReason.foundOther => strings.riderCancelFoundOther,
      CancelReason.wrongPickup => strings.riderCancelWrongPickup,
      CancelReason.other => strings.riderCancelOther,
    };

class _TripSheet extends StatelessWidget {
  const _TripSheet({
    required this.stage,
    required this.trip,
    required this.ride,
    required this.onCancel,
  });

  final ResumeStage stage;
  final Trip? trip;
  final RideRequest? ride;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    final title = switch (stage) {
      ResumeStage.driverAssigned => strings.tripDriverAssigned,
      ResumeStage.driverArriving => strings.tripDriverArriving,
      ResumeStage.driverArrived => strings.tripDriverArrived,
      ResumeStage.inProgress => strings.tripInProgress,
      _ => strings.tripCompleted,
    };

    // الإلغاء متاح قبل البدء فقط — والخادم يفرض ذلك أيضًا. إبقاء الزرّ
    // بعد البدء يَعِد بما سيُرفض.
    final canCancel = stage == ResumeStage.driverAssigned ||
        stage == ResumeStage.driverArriving ||
        stage == ResumeStage.driverArrived;

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.13),
            blurRadius: 14,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(title, style: theme.textTheme.titleLarge),
              if (trip != null) ...[
                const SizedBox(height: 14),
                _DriverCard(trip: trip!),
              ],
              if (ride != null) ...[
                const SizedBox(height: 14),
                Row(
                  children: [
                    Text(strings.fareCustomerTotal,
                        style: theme.textTheme.bodyMedium),
                    const Spacer(),
                    MoneyText(
                      ride!.fare.customerTotal,
                      style: theme.textTheme.titleLarge,
                    ),
                  ],
                ),
              ],
              if (canCancel) ...[
                const SizedBox(height: 14),
                OutlinedButton(
                  onPressed: onCancel,
                  child: Text(strings.tripCancelTrip),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _DriverCard extends StatelessWidget {
  const _DriverCard({required this.trip});

  final Trip trip;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Row(
      children: [
        CircleAvatar(
          radius: 22,
          backgroundColor: theme.colorScheme.surfaceContainerHighest,
          child: Icon(Icons.person_rounded,
              color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(trip.driverName, style: theme.textTheme.titleMedium),
              Text(
                '${trip.vehicleLabel} · ${trip.vehicleColor}',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ),
        CallButton(phone: trip.driverPhone, tooltip: strings.callDriver),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(strings.tripPlate, style: theme.textTheme.labelSmall),
            // رقم اللوحة يظهر بعد القبول وحده — قبله لا يُبثّ أصلًا.
            // وهو ما يجده الزبون على الرصيف، فيستحقّ خطًّا جدوليًّا واضحًا.
            Text(
              trip.vehiclePlate,
              textDirection: TextDirection.ltr,
              style: SoumTheme.tabular(theme.textTheme.titleMedium!),
            ),
          ],
        ),
      ],
    );
  }
}

/// ما يقوله الزبون لنفسه قبل أن يؤكّد: هل هذا الإلغاء مجّانيّ؟ نفس قاعدة
/// الخادم (trips/services/cancellation.py) بأرقام المنطقة من الإعداد —
/// والخادم يبقى الحَكَم؛ هذا إعلامٌ لا قرار.
String _cancelNotice(SoumStrings strings, Trip? trip, AreaTimings timings) {
  final assigned = trip?.arrivingAt;
  if (trip == null || assigned == null) return strings.cancelFreeNow;

  final elapsed = DateTime.now().difference(assigned);
  if (elapsed.inSeconds <= timings.cancelFreeWindowSeconds) {
    return strings.cancelFreeNow;
  }
  if (trip.arrivedAt == null &&
      elapsed.inMinutes > timings.cancelDriverLateGraceMinutes + 3) {
    return strings.cancelDriverLateFree;
  }
  return strings.cancelCountsStrike(timings.lateCancelStrikeLimit);
}
