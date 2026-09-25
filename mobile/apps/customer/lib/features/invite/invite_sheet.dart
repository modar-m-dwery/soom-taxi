/// الدعوة المباشرة — الميزة التي تميّز المنصّة.
///
/// «الزبون يرى ويختار». يرى السيارات المتاحة حوله ويدعو واحدة بعينها بدل
/// انتظار المزاد.
///
/// والقيود الثلاثة في §5.1 كلّها مطبَّقة هنا بسلوك مرئيّ لا برسالة خطأ:
///
///   `invitation.parallel_limit` → الأزرار تُعطَّل ما دامت دعوة معلّقة
///   `invitation.cooldown`       → السائق يُخفى مؤقّتًا ويُقترح غيره
///   `invitation.expired`        → عودة تلقائية إلى الخريطة
///
/// والمهلة تُختار من `invitation_ttl_options` حصرًا — أيّ قيمة أخرى
/// يرفضها الخادم بـ400، ولا معنى لعرض خيار سيُرفض.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import '../ride/ride_controller.dart';
import '../map/vehicle_marker.dart';

Future<void> showInviteSheet(BuildContext context, WidgetRef ref) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => const _InviteSheet(),
  );
}

class _InviteSheet extends ConsumerStatefulWidget {
  const _InviteSheet();

  @override
  ConsumerState<_InviteSheet> createState() => _InviteSheetState();
}

class _InviteSheetState extends ConsumerState<_InviteSheet> {
  List<NearbyVehicle>? _vehicles;
  int? _ttl;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final vehicles =
        await ref.read(rideControllerProvider.notifier).nearbyVehicles();
    if (!mounted) return;
    setState(() {
      _vehicles = vehicles;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final config = ref.watch(configProvider);
    final clock = ref.watch(clockProvider);
    final arc = ref.watch(rideControllerProvider);

    final options = config.timings.invitationTtlOptions;
    _ttl ??= config.timings.invitationTtlDefault;

    final pending = arc.invitation;

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
            Text(strings.inviteTitle, style: theme.textTheme.titleLarge),

            if (pending != null) ...[
              const SizedBox(height: 16),
              _PendingInvitation(invitation: pending, clock: clock),
            ] else ...[
              const SizedBox(height: 14),
              _TtlPicker(
                options: options,
                selected: _ttl!,
                onSelect: (value) => setState(() => _ttl = value),
              ),
              const SizedBox(height: 14),
              Flexible(child: _vehicleList(strings)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _vehicleList(SoumStrings strings) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 28),
        child: Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
      );
    }

    final vehicles = _vehicles ?? const <NearbyVehicle>[];
    if (vehicles.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 28),
        child: Center(
          child: Text(
            strings.homeCarsNearby(0),
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
      );
    }

    return ListView.separated(
      shrinkWrap: true,
      itemCount: vehicles.length,
      separatorBuilder: (_, _) => const SizedBox(height: 8),
      itemBuilder: (context, index) => _VehicleRow(
        vehicle: vehicles[index],
        onInvite: () => _invite(vehicles[index]),
      ),
    );
  }

  Future<void> _invite(NearbyVehicle vehicle) async {
    final ok = await ref
        .read(rideControllerProvider.notifier)
        .inviteDriver(vehicle.driverId, ttlSeconds: _ttl);

    if (!mounted) return;

    if (!ok) {
      final error = ref.read(rideControllerProvider).lastError;
      if (error != null) {
        final strings = SoumStrings.of(context);
        final message = switch (error.code) {
          ApiErrorCode.invitationCooldown => strings.inviteRejected,
          ApiErrorCode.invitationParallelLimit => strings.inviteWaiting,
          ApiErrorCode.invitationExpired => strings.inviteExpired,
          _ => error.detail,
        };
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(message)));
      }
      // القائمة تُعاد قراءتها: السائق الذي رفض صار في التهدئة فيُخفى.
      await _load();
    }
  }
}

class _TtlPicker extends StatelessWidget {
  const _TtlPicker({
    required this.options,
    required this.selected,
    required this.onSelect,
  });

  final List<int> options;
  final int selected;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);

    // Wrap لا Row: العنوان وثلاث رقائق لا تتّسع في 360 نقطة (فاضت 8 نقاط
    // على هاتفٍ حقيقيّ)، والرقاقة الثالثة تنزل سطرًا بدل أن تُقصّ.
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: 6,
      runSpacing: 4,
      children: [
        Padding(
          padding: const EdgeInsetsDirectional.only(end: 6),
          child: Text(strings.inviteTtl,
              style: Theme.of(context).textTheme.labelMedium),
        ),
        // الخيارات من الخادم. قيمةٌ من عندنا تُرفض بـ400 ويقرأ المستخدم
        // خطأً لا ذنب له فيه.
        for (final option in options)
          ChoiceChip(
            label: Text(
              strings.searchingTimeLeft(option),
              textDirection: TextDirection.rtl,
            ),
            visualDensity: VisualDensity.compact,
            selected: option == selected,
            onSelected: (_) => onSelect(option),
          ),
      ],
    );
  }
}

class _VehicleRow extends StatelessWidget {
  const _VehicleRow({required this.vehicle, required this.onInvite});

  final NearbyVehicle vehicle;
  final VoidCallback onInvite;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(
              vehicle.isSharing
                  ? Icons.groups_rounded
                  : Icons.local_taxi_rounded,
              color: vehicle.isSharing
                  ? theme.colorScheme.secondary
                  : theme.colorScheme.primary,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(driverShortName(vehicle.driverName), style: theme.textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(
                    // المسافة تقريبية بحكم التصميم: ~110 أمتار من الدقّة.
                    // عرضُها كرقم دقيق يَعِد بما ليس عندنا.
                    '${vehicle.vehicleLabel} · '
                    '${strings.inviteDistance(vehicle.approximateDistanceM)}',
                    style: theme.textTheme.bodySmall,
                  ),
                  if (vehicle.isSharing)
                    Text(
                      strings.inviteSeatsAvailable(vehicle.availableSeats),
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.secondary,
                      ),
                    ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                MoneyText(vehicle.quotedFare, style: theme.textTheme.titleMedium),
                const SizedBox(height: 4),
                FilledButton(
                  // `is_invited` من الخادم: دعوةٌ قائمة لهذا السائق من
                  // هذا الطلب. التعطيل هنا يمنع نداءً يردّه الخادم بـ400.
                  onPressed: vehicle.isInvited ? null : onInvite,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(72, 32),
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                  ),
                  child: Text(strings.inviteSend),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PendingInvitation extends ConsumerWidget {
  const _PendingInvitation({required this.invitation, required this.clock});

  final RideInvitation invitation;
  final ServerClock clock;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Column(
      children: [
        SoumCountdown(
          deadline: invitation.expiresAt,
          clock: clock,
          // §5.1: «أعد الزبون للخريطة تلقائيًّا» عند الانقضاء.
          onExpired: () {
            if (context.mounted) Navigator.of(context).maybePop();
          },
          builder: (context, seconds) => CountdownRing(
            secondsRemaining: seconds,
            totalSeconds: invitation.ttlSeconds,
            size: 64,
          ),
        ),
        const SizedBox(height: 14),
        Text(strings.inviteWaiting, style: theme.textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(driverShortName(invitation.driverName), style: theme.textTheme.bodyMedium),
        Text(
          '${invitation.vehicleMake} ${invitation.vehicleModel}',
          style: theme.textTheme.bodySmall,
        ),
      ],
    );
  }
}
