/// تنفيذ الرحلة — وصلتُ، ابدأ، أنهِ.
///
/// ثلاثة قيود تجعل هذه الشاشة مختلفة عن شاشة تتبّع الزبون:
///
/// **الترتيب مفروض من الخادم.** `start` قبل `arrived` يردّ
/// `trip.not_arrived`. الزرّ الظاهر وحده هو التالي في التسلسل.
///
/// **الحارس الجغرافيّ.** «وصلت» تُرفض خارج `arrival_radius_m` — حارسٌ
/// مقصود يمنع «وصلت» من مقعد المنزل، لأنّ وصولًا كاذبًا من بعيد يبدأ
/// عدّاد عدم حضور الزبون، وهو مدخل احتيال حقيقي.
///
/// **المسافة المتبقّية تُعرض قبل الردّ.** §12.3: «عندما يظهر لك هذا الردّ
/// فالسائق لم يصل فعلًا — اعرض له المسافة المتبقّية، ولا تعِد المحاولة
/// تلقائيًّا».
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../call_button.dart';
import '../../providers.dart';
import '../presence/presence_controller.dart';
import '../work/work_controller.dart';

class RunScreen extends ConsumerStatefulWidget {
  const RunScreen({super.key});

  @override
  ConsumerState<RunScreen> createState() => _RunScreenState();
}

class _RunScreenState extends ConsumerState<RunScreen> {
  final _map = OsmMapController();

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final work = ref.watch(workControllerProvider);
    final presence = ref.watch(presenceControllerProvider);

    final ride = work.ride;
    if (ride == null) return const SizedBox.shrink();

    final stage = work.stage;
    final isHeadingToPickup = stage != ResumeStage.inProgress;
    final target = isHeadingToPickup ? ride.pickup : ride.destination;
    final me = presence.lastPosition;

    return Scaffold(
      body: Stack(
        children: [
          if (target != null)
            SoumMap(
              controller: _map,
              initialCamera: MapStart(center: me ?? target, zoom: 15),
              polylines: [
                if (ride.routeGeometry != null && !isHeadingToPickup)
                  MapPolyline(
                    points: ride.routeGeometry!.points,
                    color: theme.colorScheme.primary,
                    width: 4.5,
                  ),
              ],
              circles: [
                // دائرة النطاق مرئيّة: السائق يرى متى يصير «وصلتُ»
                // مقبولًا بدل أن يجرّب ويُرفض.
                MapCircle(
                  center: target,
                  radiusMeters: (isHeadingToPickup
                          ? ref.read(configProvider).geometry.arrivalRadiusM
                          : ref.read(configProvider).geometry.dropoffRadiusM)
                      .toDouble(),
                  color: theme.colorScheme.secondary.withValues(alpha: 0.1),
                  borderColor:
                      theme.colorScheme.secondary.withValues(alpha: 0.45),
                ),
              ],
              markers: [
                MapMarker(
                  id: 'target',
                  position: target,
                  size: const Size(34, 34),
                  builder: (context) => Container(
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: theme.colorScheme.surface,
                        width: 2.5,
                      ),
                    ),
                    child: Icon(
                      isHeadingToPickup
                          ? Icons.trip_origin_rounded
                          : Icons.place_rounded,
                      size: 17,
                      color: theme.colorScheme.onPrimary,
                    ),
                  ),
                ),
                // الركّاب الآخرون في رحلة مشتركة: نقطة التقاط من لم يُلتقط
                // بعد، ليرى السائق ترتيب مشواره كاملًا.
                for (final other in work.trips)
                  if (other.ride.id != ride.id &&
                      other.ride.pickup != null &&
                      other.trip?.status != TripStatus.inProgress)
                    MapMarker(
                      id: 'other-${other.ride.id}',
                      position: other.ride.pickup!,
                      size: const Size(28, 28),
                      builder: (context) => GestureDetector(
                        onTap: () => ref
                            .read(workControllerProvider.notifier)
                            .focus(other.ride.id),
                        child: Container(
                          decoration: BoxDecoration(
                            color: theme.colorScheme.surface,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: theme.colorScheme.secondary,
                              width: 2.5,
                            ),
                          ),
                          child: Icon(
                            Icons.person_rounded,
                            size: 15,
                            color: theme.colorScheme.secondary,
                          ),
                        ),
                      ),
                    ),
                if (me != null)
                  MapMarker(
                    id: 'me',
                    position: me,
                    size: const Size(40, 40),
                    builder: (context) => Container(
                      decoration: BoxDecoration(
                        color: theme.colorScheme.secondary,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: theme.colorScheme.surface,
                          width: 2.5,
                        ),
                      ),
                      child: Icon(
                        Icons.navigation_rounded,
                        size: 20,
                        color: theme.colorScheme.onSecondary,
                      ),
                    ),
                  ),
              ],
            ),

          if (work.trips.length > 1)
            SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      for (final entry in work.trips) ...[
                        ChoiceChip(
                          avatar: Icon(
                            entry.trip?.status == TripStatus.inProgress
                                ? Icons.airline_seat_recline_normal_rounded
                                : Icons.person_pin_circle_rounded,
                            size: 18,
                          ),
                          label: Text(strings.passengerChip(
                            _firstName(entry.trip?.customerName) ??
                                '#${entry.ride.id}',
                            entry.ride.passengerCount,
                          )),
                          selected: entry.ride.id == ride.id,
                          onSelected: (_) => ref
                              .read(workControllerProvider.notifier)
                              .focus(entry.ride.id),
                        ),
                        const SizedBox(width: 8),
                      ],
                    ],
                  ),
                ),
              ),
            ),

          Align(
            alignment: Alignment.bottomCenter,
            child: _RunSheet(
              stage: stage,
              ride: ride,
              trip: work.trip,
              isBusy: work.isBusy,
              headerLabel: isHeadingToPickup
                  ? strings.runToPickup
                  : strings.runToDestination,
            ),
          ),
        ],
      ),
    );
  }
}

String? _firstName(String? full) {
  final name = full?.trim();
  if (name == null || name.isEmpty) return null;
  return name.split(RegExp(r'\s+')).first;
}

class _RunSheet extends ConsumerWidget {
  const _RunSheet({
    required this.stage,
    required this.ride,
    required this.trip,
    required this.isBusy,
    required this.headerLabel,
  });

  final ResumeStage stage;
  final RideRequest ride;
  final Trip? trip;
  final bool isBusy;
  final String headerLabel;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final controller = ref.read(workControllerProvider.notifier);
    final config = ref.watch(configProvider);

    // إعادة البناء مع كلّ نبضة موقع: المسافة تتغيّر والسائق يتحرّك.
    ref.watch(presenceControllerProvider);

    final metersToPickup = controller.metersToPickup();
    final metersToDestination = controller.metersToDestination();

    final (label, onPressed, blockedHint) = switch (stage) {
      ResumeStage.driverAssigned || ResumeStage.driverArriving => (
          strings.runArrived,
          controller.canMarkArrived ? controller.markArrived : null,
          controller.canMarkArrived
              ? null
              : strings.runTooFarPickup(config.geometry.arrivalRadiusM),
        ),
      ResumeStage.driverArrived => (
          strings.runStart,
          controller.startTrip,
          null,
        ),
      ResumeStage.inProgress => (
          strings.runComplete,
          controller.canComplete ? controller.completeTrip : null,
          controller.canComplete
              ? null
              : strings.runTooFarDropoff(config.geometry.dropoffRadiusM),
        ),
      _ => (strings.done, null, null),
    };

    final remaining = stage == ResumeStage.inProgress
        ? metersToDestination
        : metersToPickup;

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
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(headerLabel, style: theme.textTheme.titleLarge),
                  ),
                  CallButton(
                    phone: trip?.customerPhone,
                    tooltip: strings.callCustomer,
                  ),
                  const SizedBox(width: 8),
                  if (remaining != null)
                    Text(
                      strings.runRemaining(remaining),
                      style: SoumTheme.tabular(theme.textTheme.titleMedium!),
                    ),
                ],
              ),

              const SizedBox(height: 12),
              Row(
                children: [
                  Text(strings.fareDriverNet, style: theme.textTheme.bodyMedium),
                  const Spacer(),
                  MoneyText(
                    ride.fare.driverNet,
                    style: theme.textTheme.titleLarge,
                  ),
                ],
              ),

              if (blockedHint != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(11),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.tertiary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(blockedHint, style: theme.textTheme.bodySmall),
                ),
              ],

              const SizedBox(height: 14),
              FilledButton(
                // لا إعادة محاولة تلقائية: الزرّ معطَّل حتّى يتحقّق الشرط،
                // فلا يضغط السائق مرارًا على نداء يرتدّ.
                onPressed: isBusy ? null : onPressed,
                child: isBusy
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2.2),
                      )
                    : Text(label),
              ),
              // بعد الوصول: «الزبون لم يحضر» يُفتح بعد انتظارٍ كامل — لا
              // يُحسب على السائق، ويُعوَّض عن مشواره.
              if (stage == ResumeStage.driverArrived &&
                  trip?.arrivedAt != null) ...[
                const SizedBox(height: 8),
                _NoShowButton(
                  arrivedAt: trip!.arrivedAt!,
                  wait: Duration(minutes: config.timings.cancelWaitMinutes),
                  isBusy: isBusy,
                  onPressed: () => _confirmNoShow(context, ref),
                ),
              ],
              // الإلغاء قبل البدء وحده: بعده نزاعٌ لا إلغاء (الخادم يرفض).
              if (stage != ResumeStage.inProgress && trip != null) ...[
                const SizedBox(height: 4),
                TextButton(
                  onPressed: isBusy ? null : () => _confirmCancel(context, ref),
                  child: Text(strings.runCancel),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmNoShow(BuildContext context, WidgetRef ref) async {
    final strings = SoumStrings.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.runNoShowConfirmTitle),
        content: Text(strings.runNoShowConfirmBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(strings.actionBack),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(strings.actionConfirm),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    final messenger = ScaffoldMessenger.of(context);
    final result = await ref
        .read(workControllerProvider.notifier)
        .reportNoShow(strings.runNoShow);
    if (!result.ok) {
      if (!context.mounted) return;
      final error = ref.read(workControllerProvider).failure;
      if (error != null) showApiError(context, error);
      return;
    }
    // لا فحص `mounted` هنا: نجاح «لم يحضر» يُنهي الرحلة فتُغلق هذه الشاشة
    // قبل أن نصل — والرسالة (ومعها مبلغ التعويض) على مِرسال التطبيق الذي
    // أخذناه قبل الانتظار. وُجد بالتصوير: التعويض سُجّل ولم يرَه السائق.
    final compensation = result.compensation;
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          compensation == null
              ? strings.runNoShowDone
              : strings.runNoShowCompensated(compensation.format()),
        ),
      ),
    );
  }

  Future<void> _confirmCancel(BuildContext context, WidgetRef ref) async {
    final strings = SoumStrings.of(context);
    // النصّ للإدارة، والرمز للعدّ: «عطل بالسيارة» مسموحٌ مرّتين بالشهر،
    // والنمط يُقرأ من الرموز لا من نصٍّ حرّ.
    final reasons = [
      (strings.cancelReasonCar, DriverCancelReason.carProblem),
      (strings.cancelReasonNoAnswer, DriverCancelReason.customerUnreachable),
      (strings.cancelReasonFar, DriverCancelReason.roadBlocked),
      (strings.cancelReasonOther, DriverCancelReason.other),
    ];

    final reason = await showModalBottomSheet<(String, DriverCancelReason)>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(strings.runCancelTitle,
                  style: Theme.of(sheetContext).textTheme.titleLarge),
              const SizedBox(height: 6),
              Text(strings.runCancelWarning,
                  style: Theme.of(sheetContext).textTheme.bodySmall),
              const SizedBox(height: 12),
              for (final option in reasons)
                ListTile(
                  title: Text(option.$1),
                  trailing: const Icon(Icons.chevron_left_rounded),
                  onTap: () => Navigator.pop(sheetContext, option),
                ),
            ],
          ),
        ),
      ),
    );
    if (reason == null || !context.mounted) return;

    final ok = await ref
        .read(workControllerProvider.notifier)
        .cancelTrip(reason.$1, code: reason.$2);
    if (!ok && context.mounted) {
      final error = ref.read(workControllerProvider).failure;
      if (error != null) showApiError(context, error);
    }
  }
}

/// «الزبون لم يحضر» — معطّل حتّى تنقضي مهلة الانتظار، بعدٍّ تنازليّ ظاهر.
///
/// الخادم هو الحكم (يرفض قبل المهلة ويقول كم بقي)، والعدّاد هنا كي لا
/// يضغط السائق زرًّا سيُرفض. الوقت من `arrived_at` الذي سجّله الخادم لا من
/// لحظة ضغط السائق «وصلت».
class _NoShowButton extends StatefulWidget {
  const _NoShowButton({
    required this.arrivedAt,
    required this.wait,
    required this.isBusy,
    required this.onPressed,
  });

  final DateTime arrivedAt;
  final Duration wait;
  final bool isBusy;
  final VoidCallback onPressed;

  @override
  State<_NoShowButton> createState() => _NoShowButtonState();
}

class _NoShowButtonState extends State<_NoShowButton> {
  Timer? _tick;

  Duration get _left {
    final left = widget.arrivedAt.add(widget.wait).difference(DateTime.now());
    return left.isNegative ? Duration.zero : left;
  }

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {});
      if (_left == Duration.zero) _tick?.cancel();
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final left = _left;
    final ready = left == Duration.zero;
    final clock =
        '${left.inMinutes}:${(left.inSeconds % 60).toString().padLeft(2, '0')}';

    return OutlinedButton.icon(
      onPressed: ready && !widget.isBusy ? widget.onPressed : null,
      icon: const Icon(Icons.person_off_outlined),
      label: Text(ready ? strings.runNoShow : strings.runNoShowWait(clock)),
    );
  }
}
