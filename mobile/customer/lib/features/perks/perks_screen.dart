/// اشتراك الصباح والدعوات — ما وعدت به خطّة التسعين يومًا للزبون الدائم.
///
/// شاشة واحدة بقسمين:
///   • «اشتراك الصباح»: مشوارٌ يوميّ يُطلب تلقائيًّا قبل موعده بنصف ساعة.
///     الخادم يُنشئ الطلب؛ التطبيق لا يحتاج أن يكون مفتوحًا.
///   • «زبون يجلب زبونًا»: رمزي، ورصيدي، وإدخال رمز صديق قبل رحلتي الأولى.
///
/// خصم أوّل مشوار لا زرّ له: يُطبَّق في الخادم عند الدفع، وتُظهره شاشة
/// الختام سطرًا مستقلًّا. هنا نقول فقط إن كان ما زال ينتظر.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers.dart';
import '../map/vehicle_marker.dart';

final mySubscriptionsProvider =
    FutureProvider.autoDispose<List<RideSubscription>>(
  (ref) => ref.read(soumProvider).rides.subscriptions(),
);

final myReferralProvider = FutureProvider.autoDispose<Referral>(
  (ref) => ref.read(soumProvider).payments.myReferral(),
);

class PerksScreen extends ConsumerWidget {
  const PerksScreen({super.key, required this.pickup});

  /// موقع الزبون الآن — نقطة انطلاق الاشتراك الجديد.
  final GeoPoint pickup;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(strings.perksTitle)),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(mySubscriptionsProvider);
          ref.invalidate(myReferralProvider);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _SectionTitle(
              icon: Icons.wb_twilight_rounded,
              title: strings.perksSubscriptionsSection,
            ),
            _SubscriptionsSection(pickup: pickup),
            const SizedBox(height: 28),
            _SectionTitle(
              icon: Icons.card_giftcard_rounded,
              title: strings.perksReferralSection,
            ),
            const _ReferralSection(),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Icon(icon, size: 20, color: theme.colorScheme.primary),
          const SizedBox(width: 8),
          Text(title, style: theme.textTheme.titleMedium),
        ],
      ),
    );
  }
}

// ------------------------------------------------------------ اشتراك الصباح

class _SubscriptionsSection extends ConsumerWidget {
  const _SubscriptionsSection({required this.pickup});

  final GeoPoint pickup;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final subscriptions = ref.watch(mySubscriptionsProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        subscriptions.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(24),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
          ),
          error: (error, _) => ApiErrorView(
            failure: error is ApiException
                ? error
                : ApiException(
                    statusCode: 0,
                    code: ApiErrorCode.networkUnavailable,
                    detail: '$error',
                  ),
            onRetry: () => ref.invalidate(mySubscriptionsProvider),
          ),
          data: (rows) => rows.isEmpty
              ? Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(strings.perksSubscriptionsEmpty,
                        style: theme.textTheme.bodyMedium),
                  ),
                )
              : Column(
                  children: [
                    for (final row in rows)
                      _SubscriptionTile(
                        subscription: row,
                        onCancel: () => _cancel(context, ref, row),
                      ),
                  ],
                ),
        ),
        const SizedBox(height: 10),
        FilledButton.icon(
          onPressed: () => _create(context, ref),
          icon: const Icon(Icons.add_alarm_rounded),
          label: Text(strings.perksSubscriptionAdd),
        ),
      ],
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final created = await showModalBottomSheet<RideSubscription>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => _NewSubscriptionSheet(pickup: pickup),
    );
    if (created == null || !context.mounted) return;
    ref.invalidate(mySubscriptionsProvider);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(SoumStrings.of(context).perksSubscriptionCreated),
        ),
      );
  }

  Future<void> _cancel(
    BuildContext context,
    WidgetRef ref,
    RideSubscription row,
  ) async {
    final strings = SoumStrings.of(context);
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        content: Text(strings.perksSubscriptionCancelConfirm),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(strings.actionBack),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(strings.perksSubscriptionCancel),
          ),
        ],
      ),
    );
    if (sure != true || !context.mounted) return;
    try {
      await ref.read(soumProvider).rides.cancelSubscription(row.id);
    } on ApiException catch (error) {
      if (context.mounted) showApiError(context, error);
      return;
    }
    ref.invalidate(mySubscriptionsProvider);
  }
}

class _SubscriptionTile extends StatelessWidget {
  const _SubscriptionTile({required this.subscription, required this.onCancel});

  final RideSubscription subscription;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final next = subscription.nextOccurrence;
    final locale = Localizations.localeOf(context).toString();

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        _hhmm(subscription.departureTime),
                        style: SoumTheme.tabular(theme.textTheme.titleLarge!),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          subscription.label.isEmpty
                              ? strings.perksSubscriptionsSection
                              : subscription.label,
                          style: theme.textTheme.titleSmall,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    weekdayNames(strings, subscription.effectiveWeekdays)
                        .join(strings.listSeparator),
                    style: theme.textTheme.bodySmall,
                  ),
                  if (next != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      strings.perksSubscriptionNext(
                        DateFormat(strings.perksNextFormat, locale).format(next),
                      ),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.tertiary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            IconButton(
              tooltip: strings.perksSubscriptionCancel,
              icon: const Icon(Icons.delete_outline_rounded),
              onPressed: onCancel,
            ),
          ],
        ),
      ),
    );
  }

  /// «07:30:00» من الخادم → «07:30».
  static String _hhmm(String raw) =>
      raw.length >= 5 ? raw.substring(0, 5) : raw;
}

/// أسماء الأيام بترتيب أسبوع سوريّ (الأحد أوّلًا).
List<String> weekdayNames(SoumStrings strings, List<int> days) {
  const order = [6, 0, 1, 2, 3, 4, 5];
  return [
    for (final day in order)
      if (days.contains(day)) weekdayName(strings, day),
  ];
}

String weekdayName(SoumStrings strings, int day) => switch (day) {
      0 => strings.dayMon,
      1 => strings.dayTue,
      2 => strings.dayWed,
      3 => strings.dayThu,
      4 => strings.dayFri,
      5 => strings.daySat,
      _ => strings.daySun,
    };

class _NewSubscriptionSheet extends ConsumerStatefulWidget {
  const _NewSubscriptionSheet({required this.pickup});

  final GeoPoint pickup;

  @override
  ConsumerState<_NewSubscriptionSheet> createState() =>
      _NewSubscriptionSheetState();
}

class _NewSubscriptionSheetState extends ConsumerState<_NewSubscriptionSheet> {
  final _label = TextEditingController();
  final _map = OsmMapController();

  TimeOfDay _time = const TimeOfDay(hour: 7, minute: 30);
  final Set<int> _days = {...syrianWorkweek};
  GeoPoint? _destination;
  String? _vehicleType;
  bool _submitting = false;

  @override
  void dispose() {
    _label.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final config = ref.watch(configProvider);
    final destination = _destination;

    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(strings.perksSubscriptionAdd,
                style: theme.textTheme.titleLarge),
            const SizedBox(height: 14),
            TextField(
              controller: _label,
              decoration: InputDecoration(
                labelText: strings.perksSubscriptionLabel,
                hintText: strings.perksSubscriptionLabelHint,
              ),
              textInputAction: TextInputAction.done,
            ),
            const SizedBox(height: 14),

            // الموعد بالساعة المحلّية؛ الخادم يفسّرها بتوقيت دمشق.
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.schedule_rounded),
              title: Text(strings.perksSubscriptionTime),
              trailing: Text(
                _time.format(context),
                style: SoumTheme.tabular(theme.textTheme.titleLarge!),
              ),
              onTap: () async {
                final picked = await showTimePicker(
                  context: context,
                  initialTime: _time,
                );
                if (picked != null) setState(() => _time = picked);
              },
            ),

            Text(strings.perksSubscriptionDays,
                style: theme.textTheme.labelLarge),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final day in const [6, 0, 1, 2, 3, 4, 5])
                  FilterChip(
                    label: Text(weekdayName(strings, day)),
                    selected: _days.contains(day),
                    onSelected: (on) => setState(() {
                      if (on) {
                        _days.add(day);
                      } else if (_days.length > 1) {
                        _days.remove(day);
                      }
                    }),
                  ),
              ],
            ),
            const SizedBox(height: 14),

            Row(
              children: [
                Icon(Icons.trip_origin_rounded,
                    size: 18, color: theme.colorScheme.secondary),
                const SizedBox(width: 8),
                Text(strings.perksSubscriptionPickup,
                    style: theme.textTheme.bodyMedium),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(Icons.place_rounded,
                    size: 18, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  destination == null
                      ? strings.perksSubscriptionPickDestination
                      : strings.perksSubscriptionDestinationSet,
                  style: theme.textTheme.bodyMedium,
                ),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: SizedBox(
                height: 220,
                child: SoumMap(
                  controller: _map,
                  initialCamera: MapStart(center: widget.pickup, zoom: 14),
                  markers: [
                    pointMarker(
                      id: 'pickup',
                      position: widget.pickup,
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
                  ],
                  onTap: (point) => setState(() => _destination = point),
                ),
              ),
            ),
            const SizedBox(height: 14),

            DropdownButtonFormField<String?>(
              initialValue: _vehicleType,
              decoration: InputDecoration(labelText: strings.vehicleType),
              items: [
                DropdownMenuItem(value: null, child: Text(strings.vehicleAny)),
                for (final category in config.vehicleCategories)
                  DropdownMenuItem(
                    value: category.code,
                    child: Text(category.name),
                  ),
              ],
              onChanged: (value) => setState(() => _vehicleType = value),
            ),
            const SizedBox(height: 18),

            FilledButton(
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(strings.perksSubscriptionAdd),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final strings = SoumStrings.of(context);
    final destination = _destination;
    if (destination == null) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(content: Text(strings.perksSubscriptionNeedDestination)),
        );
      return;
    }

    final hh = _time.hour.toString().padLeft(2, '0');
    final mm = _time.minute.toString().padLeft(2, '0');

    setState(() => _submitting = true);
    try {
      final created = await ref.read(soumProvider).rides.createSubscription(
            pickup: widget.pickup,
            destination: destination,
            departureTime: '$hh:$mm',
            label: _label.text.trim(),
            weekdays: _days.toList()..sort(),
            requestedVehicleType: _vehicleType,
          );
      if (mounted) Navigator.of(context).pop(created);
    } on ApiException catch (error) {
      if (mounted) showApiError(context, error);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }
}

// ------------------------------------------------------------ الدعوات

class _ReferralSection extends ConsumerStatefulWidget {
  const _ReferralSection();

  @override
  ConsumerState<_ReferralSection> createState() => _ReferralSectionState();
}

class _ReferralSectionState extends ConsumerState<_ReferralSection> {
  final _code = TextEditingController();
  bool _applying = false;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final referral = ref.watch(myReferralProvider);

    return referral.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(24),
        child: Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
      ),
      error: (error, _) => ApiErrorView(
        failure: error is ApiException
            ? error
            : ApiException(
                statusCode: 0,
                code: ApiErrorCode.networkUnavailable,
                detail: '$error',
              ),
        onRetry: () => ref.invalidate(myReferralProvider),
      ),
      data: (data) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(strings.perksReferralMyCode,
                      style: theme.textTheme.bodySmall),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Expanded(
                        child: SelectableText(
                          data.referralCode,
                          textDirection: TextDirection.ltr,
                          style: SoumTheme.tabular(
                            theme.textTheme.headlineMedium!.copyWith(
                              letterSpacing: 4,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                      IconButton(
                        tooltip: strings.perksReferralCopied,
                        icon: const Icon(Icons.copy_rounded),
                        onPressed: () => _copy(data.referralCode),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(strings.perksReferralExplain,
                      style: theme.textTheme.bodySmall),
                  const SizedBox(height: 12),
                  // واتساب أوّلًا: هو قناة الإطلاق في الخطّة، ورابط
                  // `wa.me` يفتح التطبيق بنصٍّ جاهز بلا حزمة مشاركة.
                  FilledButton.tonalIcon(
                    onPressed: () => _share(data.referralCode),
                    icon: const Icon(Icons.share_rounded),
                    label: Text(strings.perksReferralShare),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Text(strings.perksCreditBalance,
                          style: theme.textTheme.bodyMedium),
                      const Spacer(),
                      MoneyText(data.creditBalance,
                          style: theme.textTheme.titleLarge),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Icon(
                        data.firstRideDiscountAvailable
                            ? Icons.local_offer_rounded
                            : Icons.check_circle_outline_rounded,
                        size: 18,
                        color: theme.colorScheme.secondary,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          data.firstRideDiscountAvailable
                              ? strings.perksFirstRideAvailable
                              : strings.perksFirstRideUsed,
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (data.hasReferrer)
                    Text(
                      strings.perksReferralLinked(data.referredByCode!),
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.tertiary,
                      ),
                    )
                  else if (data.firstRideDiscountAvailable)
                    // الرمز يُدخل قبل الرحلة الأولى فقط — الخادم يرفضه
                    // بعدها، فلا نعرض الحقل حين لا فائدة منه.
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _code,
                            textCapitalization: TextCapitalization.characters,
                            textDirection: TextDirection.ltr,
                            maxLength: 6,
                            decoration: InputDecoration(
                              labelText: strings.perksReferralEnter,
                              hintText: strings.perksReferralEnterHint,
                              counterText: '',
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        // الصفّ داخل عمود ممدود: بلا عرضٍ صريح يأخذ الزرّ
                        // قيدًا لا نهائيًّا ويسقط العمود كلّه من الرسم.
                        SizedBox(
                          width: 96,
                          child: FilledButton(
                            onPressed: _applying ? null : _apply,
                            child: Text(strings.perksReferralApply),
                          ),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _copy(String code) async {
    await Clipboard.setData(ClipboardData(text: code));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(SoumStrings.of(context).perksReferralCopied)),
      );
  }

  Future<void> _share(String code) async {
    final text = SoumStrings.of(context).perksReferralShareText(code);
    final uri = Uri.https('wa.me', '/', {'text': text});
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened) await _copy(code);
  }

  Future<void> _apply() async {
    final code = _code.text.trim();
    if (code.isEmpty) return;
    setState(() => _applying = true);
    try {
      final result =
          await ref.read(soumProvider).payments.applyReferralCode(code);
      if (!mounted) return;
      ref.invalidate(myReferralProvider);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(
            content: Text(SoumStrings.of(context)
                .perksReferralApplied(result.referredByCode ?? code)),
          ),
        );
    } on ApiException catch (error) {
      if (mounted) showApiError(context, error);
    } finally {
      if (mounted) setState(() => _applying = false);
    }
  }
}
