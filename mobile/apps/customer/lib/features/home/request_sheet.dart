/// بطاقة الطلب — ثلاث طرق للطلب بواجهة واحدة.
///
/// الزبون لا يفكّر بـ«درجة خدمة» بل بسؤال واحد: مَن يختار السائق؟
///
/// - **عروض**: السائقون يرسلون أسعارهم والزبون يختار. قلب سووم.
/// - **الأقرب**: الخادم يدعو أقرب سائق، ثمّ التالي إن رفض أو صمت.
/// - **اختر سيارتك**: الزبون يلمس السيارة التي يريدها على الخريطة.
///
/// والأنماط (`mode`) تبقى من `ride_modes` لا من تعداد في التطبيق (§12.3):
/// «الأقرب» و«اختر سيارتك» يحتاجان نمطًا تفعّل فيه المنطقة الدعوة المباشرة،
/// فإن أطفأها المشغّل اختفى الخياران فورًا — لا بعد إصدار على المتجر.
///
/// و§3 يفصل محورين لا يجوز خلطهما: `mode` درجة الخدمة، و`trip_category`
/// نطاق الرحلة. «بين مدينتين بدرجة اقتصادية» تركيبٌ صحيح ومطلوب.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import '../map/vehicle_marker.dart';

enum DispatchStyle { offers, nearest, pick }

/// الأنماط التي تعمل بالدعوة المباشرة، بترتيب التفضيل لكلّ طريقة.
const _nearestModes = ['fast', 'express'];
const _pickModes = ['express', 'fast'];

/// النمط الذي تُرسَل به كلّ طريقة، أو null إن لم تتِحها المنطقة.
///
/// [shared]: الزبون يريد مشاركة الرحلة. بالعروض يصير الطلب `shared`؛ وبـ
/// «الأقرب» و«اختر سيارتك» لا يصحّ إلّا إن فعّلت المنطقة الدعوة للمشترك.
String? modeForStyle(
  DispatchStyle style,
  AppConfig config, {
  String? offersMode,
  bool shared = false,
}) {
  final modes = config.rideModes;
  // المشغّل أطفأ الطريقة: تختفي، والخادم يرفضها أصلًا.
  if (style == DispatchStyle.nearest && !config.feature('nearest')) return null;
  if (style == DispatchStyle.pick && !config.feature('pick_car')) return null;
  if (shared) {
    if (!modes.contains('shared')) return null;
    if (style == DispatchStyle.offers) return 'shared';
    return config.supportsInvitation('shared') ? 'shared' : null;
  }
  String? firstInvitable(List<String> preferred) => preferred
      .where((m) => modes.contains(m) && config.supportsInvitation(m))
      .firstOrNull;

  return switch (style) {
    DispatchStyle.offers =>
      offersMode != null && modes.contains(offersMode)
          ? offersMode
          : offerModes(config).firstOrNull,
    DispatchStyle.nearest => firstInvitable(_nearestModes),
    DispatchStyle.pick => firstInvitable(_pickModes),
  };
}

/// درجات المزاد: كلّ نمط غير «سريع/فوري» و«مشترك» (له مفتاحه)، و«عادي» أوّلًا.
List<String> offerModes(AppConfig config) {
  final modes = config.rideModes
      .where((m) => !_nearestModes.contains(m) && m != 'shared')
      .toList(growable: false);
  if (modes.isEmpty) return config.rideModes;
  return [
    if (modes.contains('standard')) 'standard',
    ...modes.where((m) => m != 'standard'),
  ];
}

class RideRequestDraft {
  const RideRequestDraft({
    required this.pickup,
    required this.destination,
    required this.mode,
    required this.passengerCount,
    required this.category,
    this.vehicleType,
    this.scheduledAt,
    this.originCity,
    this.destinationCity,
    this.searchRadiusKm,
    this.autoDispatch = false,
    this.inviteDriverId,
  });

  final GeoPoint pickup;
  final GeoPoint destination;
  final String mode;
  final int passengerCount;
  final TripCategory category;
  final String? vehicleType;
  final DateTime? scheduledAt;
  final String? originCity;
  final String? destinationCity;
  final double? searchRadiusKm;
  final bool autoDispatch;

  /// «اختر سيارتك»: يُدعى هذا السائق فور إنشاء الطلب.
  final int? inviteDriverId;
}

class RequestSheet extends ConsumerStatefulWidget {
  const RequestSheet({
    super.key,
    required this.pickup,
    required this.destination,
    required this.onPickDestination,
    required this.onSubmit,
    this.style = DispatchStyle.offers,
    this.preset,
    this.selectedVehicle,
    this.onStyleChanged,
    this.onRadiusChanged,
  });

  final GeoPoint pickup;
  final GeoPoint? destination;
  final VoidCallback onPickDestination;
  final Future<void> Function(RideRequestDraft) onSubmit;

  /// الطريقة يملكها الأب: لمسُ سيارة على الخريطة يحوّلها إلى «اختر سيارتك».
  final DispatchStyle style;

  /// خدمةٌ اختارها الزبون من الشريط (مشترك، بين المدن، سرفيس) — تضبط
  /// البطاقة عليها. رقمٌ متزايد مع الرمز كي تُطبَّق حتّى لو تكرّر الرمز.
  final (String, int)? preset;

  /// السيارة التي لمسها الزبون على الخريطة — لطريقة «اختر سيارتك».
  final NearbyVehicle? selectedVehicle;

  final ValueChanged<DispatchStyle>? onStyleChanged;

  /// الخريطة ترسم دائرة النطاق المختار وتُخفي ما خارجها.
  final ValueChanged<double?>? onRadiusChanged;

  @override
  ConsumerState<RequestSheet> createState() => _RequestSheetState();
}

class _RequestSheetState extends ConsumerState<RequestSheet> {
  String? _offersMode;
  double? _radiusKm;
  bool _shared = false;
  bool _showMore = false;

  String? _vehicleType;
  int _passengers = 1;
  TripCategory _category = TripCategory.city;
  final _originCity = TextEditingController();
  final _destinationCity = TextEditingController();

  RouteResult? _route;
  bool _routing = false;
  bool _submitting = false;

  /// موعد الانطلاق حين لا يكون «الآن». المجدولة طلبٌ عاديّ بموعد: الخادم
  /// يبحث عن سائق قبل الموعد لا لحظة الإنشاء. وهي للعروض وحدها: «الأقرب»
  /// و«اختر سيارتك» يعنيان سيارةً موجودة الآن.
  DateTime? _scheduledAt;

  @override
  void dispose() {
    _originCity.dispose();
    _destinationCity.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(RequestSheet old) {
    super.didUpdateWidget(old);
    if (old.destination != widget.destination) _estimate();
    final preset = widget.preset;
    if (preset != null && preset != old.preset) _applyPreset(preset.$1);
  }

  void _applyPreset(String code) {
    setState(() {
      switch (code) {
        case 'shared':
          _shared = true;
          _category = TripCategory.city;
        case 'intercity':
          _shared = false;
          _category = TripCategory.intercity;
          _showMore = true;
        case 'service_line':
          _shared = false;
          _category = TripCategory.serviceLine;
          _showMore = true;
        default:
          _shared = false;
          _category = TripCategory.city;
      }
    });
    if (code == 'intercity' || code == 'service_line' || code == 'shared') {
      if (widget.style != DispatchStyle.offers) {
        widget.onStyleChanged?.call(DispatchStyle.offers);
      }
    }
  }

  /// تقدير المسافة والزمن قبل الطلب.
  ///
  /// النقطة لا تنكسر عند تعذّر المزوّد: تعود بتقدير و`source: estimated`
  /// (§9.2). فنعرض «سعر تقريبي» بدل أن نُخفي الرقم أو نُظهر خطأ.
  Future<void> _estimate() async {
    final destination = widget.destination;
    if (destination == null) {
      setState(() => _route = null);
      return;
    }

    setState(() => _routing = true);
    try {
      final route = await ref
          .read(soumProvider)
          .maps
          .route(origin: widget.pickup, destination: destination);
      if (mounted) setState(() => _route = route);
    } on ApiException {
      // تقديرٌ فاشل لا يمنع الطلب: الخادم يحسب السعر بنفسه عند الإنشاء.
      if (mounted) setState(() => _route = null);
    } finally {
      if (mounted) setState(() => _routing = false);
    }
  }

  void _selectStyle(DispatchStyle style) {
    if (style != DispatchStyle.offers) setState(() => _scheduledAt = null);
    widget.onStyleChanged?.call(style);
  }

  void _selectRadius(double km) {
    setState(() => _radiusKm = km);
    widget.onRadiusChanged?.call(km);
  }

  bool _canSubmit(String? mode, DispatchStyle style) {
    if (widget.destination == null || mode == null || _submitting) return false;
    if (style == DispatchStyle.pick && widget.selectedVehicle == null) {
      return false;
    }
    if (_category.requiresCities) {
      return _originCity.text.trim().isNotEmpty &&
          _destinationCity.text.trim().isNotEmpty;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final config = ref.watch(configProvider);

    final canShare = config.rideModes.contains('shared');
    final styles = [
      for (final style in DispatchStyle.values)
        if (modeForStyle(style, config, shared: _shared) != null) style,
    ];
    // المشغّل أطفأ الدعوة المباشرة والزبون على طريقةٍ اختفت: نعود للعروض.
    final style = styles.contains(widget.style) || styles.isEmpty
        ? widget.style
        : styles.first;

    final mode = modeForStyle(
      style,
      config,
      offersMode: _offersMode,
      shared: _shared,
    );
    final classes = offerModes(config);

    final radii = config.geometry.searchRadiusOptionsKm;
    final radius = _radiusKm != null && radii.contains(_radiusKm)
        ? _radiusKm
        : radii.lastOrNull;

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * 0.64,
      ),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
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
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
          child: Column(
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
              const SizedBox(height: 12),

              _DestinationRow(
                destination: widget.destination,
                onPick: widget.onPickDestination,
              ),

              if (styles.length > 1) ...[
                const SizedBox(height: 14),
                Row(
                  children: [
                    for (final option in styles) ...[
                      if (option != styles.first) const SizedBox(width: 8),
                      Expanded(
                        child: _StyleCard(
                          style: option,
                          isSelected: option == style,
                          onTap: () => _selectStyle(option),
                        ),
                      ),
                    ],
                  ],
                ),
              ],

              if (canShare) ...[
                const SizedBox(height: 10),
                _ShareToggle(
                  value: _shared,
                  onChanged: (value) {
                    setState(() => _shared = value);
                    // طريقةٌ لا تصحّ مع المشاركة في هذه المنطقة: نعود للعروض.
                    if (modeForStyle(style, config, shared: value) == null) {
                      _selectStyle(DispatchStyle.offers);
                    }
                  },
                ),
              ],

              if (style == DispatchStyle.pick) ...[
                const SizedBox(height: 10),
                _PickedCar(vehicle: widget.selectedVehicle),
              ],

              if (radii.length > 1) ...[
                const SizedBox(height: 12),
                _RadiusPicker(
                  options: radii,
                  selected: radius,
                  onSelect: _selectRadius,
                ),
              ],

              const SizedBox(height: 6),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: TextButton.icon(
                  onPressed: () => setState(() => _showMore = !_showMore),
                  icon: Icon(
                    _showMore ? Icons.expand_less_rounded : Icons.tune_rounded,
                    size: 18,
                  ),
                  label: Text(strings.moreOptions),
                ),
              ),

              if (_showMore) ...[
                if (style == DispatchStyle.offers && classes.length > 1) ...[
                  _ClassPicker(
                    modes: classes,
                    selected: mode,
                    onSelect: (m) => setState(() => _offersMode = m),
                  ),
                  const SizedBox(height: 10),
                ],
                _CategoryPicker(
                  allowed: config.tripCategories,
                  selected: _category,
                  onSelect: (category) => setState(() => _category = category),
                ),
                if (_category.requiresCities) ...[
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _originCity,
                          decoration: InputDecoration(
                            labelText: strings.cityOrigin,
                            isDense: true,
                          ),
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TextField(
                          controller: _destinationCity,
                          decoration: InputDecoration(
                            labelText: strings.cityDestination,
                            isDense: true,
                          ),
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                    ],
                  ),
                ],
                if (style == DispatchStyle.offers &&
                    config.feature('scheduled_rides')) ...[
                  const SizedBox(height: 12),
                  _WhenRow(
                    scheduledAt: _scheduledAt,
                    onNow: () => setState(() => _scheduledAt = null),
                    onPick: _pickSchedule,
                  ),
                ],
                const SizedBox(height: 12),
                _PassengerAndVehicle(
                  categories: config.vehicleCategories,
                  passengers: _passengers,
                  vehicleType: _vehicleType,
                  onPassengers: (count) => setState(() => _passengers = count),
                  onVehicle: (type) => setState(() => _vehicleType = type),
                ),
              ],

              if (_routing) ...[
                const SizedBox(height: 10),
                const LinearProgressIndicator(minHeight: 2),
              ] else if (_route != null) ...[
                const SizedBox(height: 10),
                _RouteEstimate(route: _route!),
              ],

              const SizedBox(height: 14),
              FilledButton(
                onPressed: _canSubmit(mode, style)
                    ? () => _submit(mode!, radius, style)
                    : null,
                child: _submitting
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2.2),
                      )
                    : Text(switch (style) {
                        DispatchStyle.nearest => strings.requestNearest,
                        DispatchStyle.pick => strings.requestPicked,
                        DispatchStyle.offers =>
                          _scheduledAt == null
                              ? strings.requestRide
                              : strings.requestScheduledRide,
                      }),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pickSchedule() async {
    final now = DateTime.now();
    final initial = _scheduledAt ?? now.add(const Duration(hours: 1));
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: now,
      lastDate: now.add(const Duration(days: 30)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initial),
    );
    if (time == null || !mounted) return;
    final when = DateTime(
      date.year,
      date.month,
      date.day,
      time.hour,
      time.minute,
    );
    // موعدٌ مضى يعني «الآن» فعليًّا؛ الخادم يرفضه، فلا نعرضه أصلًا.
    if (when.isBefore(now.add(const Duration(minutes: 10)))) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(content: Text(SoumStrings.of(context).scheduleTooSoon)),
        );
      return;
    }
    setState(() => _scheduledAt = when);
  }

  Future<void> _submit(String mode, double? radius, DispatchStyle style) async {
    setState(() => _submitting = true);
    try {
      await widget.onSubmit(
        RideRequestDraft(
          pickup: widget.pickup,
          destination: widget.destination!,
          mode: mode,
          passengerCount: _passengers,
          category: _category,
          vehicleType: _vehicleType,
          scheduledAt: style == DispatchStyle.offers ? _scheduledAt : null,
          originCity: _category.requiresCities ? _originCity.text.trim() : null,
          destinationCity: _category.requiresCities
              ? _destinationCity.text.trim()
              : null,
          searchRadiusKm: radius,
          autoDispatch: style == DispatchStyle.nearest,
          inviteDriverId: style == DispatchStyle.pick
              ? widget.selectedVehicle?.driverId
              : null,
        ),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }
}

/// بطاقة طريقة الطلب. المختارة لوحة التاكسي مقلوبة: حبرٌ داكن وأيقونة
/// صفراء — تُقرأ من بعيد ولا تتنافس مع زرّ «اطلب» الأصفر تحتها.
class _StyleCard extends StatelessWidget {
  const _StyleCard({
    required this.style,
    required this.isSelected,
    required this.onTap,
  });

  final DispatchStyle style;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    final (label, hint, icon) = switch (style) {
      DispatchStyle.offers => (
        strings.dispatchOffers,
        strings.dispatchOffersHint,
        Icons.gavel_rounded,
      ),
      DispatchStyle.nearest => (
        strings.dispatchNearest,
        strings.dispatchNearestHint,
        Icons.near_me_rounded,
      ),
      DispatchStyle.pick => (
        strings.dispatchPick,
        strings.dispatchPickHint,
        Icons.touch_app_rounded,
      ),
    };

    final ink = isSelected ? scheme.primary : scheme.onSurface;

    return Semantics(
      selected: isSelected,
      button: true,
      child: Material(
        color: isSelected ? scheme.onSurface : scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(10, 10, 10, 9),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon, size: 20, color: ink),
                const SizedBox(height: 4),
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: ink,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  hint,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: isSelected
                        ? scheme.surface.withValues(alpha: 0.72)
                        : null,
                    height: 1.3,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// «شارك الرحلة» — مفتاحٌ ظاهر لا خيارٌ مدفون: الأرخص هو ما يبحث عنه
/// أغلب الزبائن، والمشاركة هي الأرخص.
class _ShareToggle extends StatelessWidget {
  const _ShareToggle({required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Material(
      color: value
          ? theme.colorScheme.secondary.withValues(alpha: 0.1)
          : theme.colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(12),
      child: SwitchListTile(
        value: value,
        onChanged: onChanged,
        dense: true,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        secondary: Icon(
          Icons.groups_rounded,
          color: theme.colorScheme.secondary,
        ),
        title: Text(strings.shareRide, style: theme.textTheme.titleMedium),
        subtitle: Text(strings.shareRideHint, style: theme.textTheme.bodySmall),
      ),
    );
  }
}

/// السيارة المختارة من الخريطة، أو دعوةٌ لاختيار واحدة.
class _PickedCar extends StatelessWidget {
  const _PickedCar({required this.vehicle});

  final NearbyVehicle? vehicle;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final car = vehicle;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: car == null
              ? theme.colorScheme.outlineVariant
              : theme.colorScheme.onSurface,
        ),
      ),
      child: car == null
          ? Row(
              children: [
                Icon(
                  Icons.touch_app_rounded,
                  size: 18,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    strings.pickTapCar,
                    style: theme.textTheme.bodySmall,
                  ),
                ),
              ],
            )
          : Row(
              children: [
                Icon(
                  Icons.local_taxi_rounded,
                  size: 20,
                  color: theme.colorScheme.tertiary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    strings.pickSelected(driverShortName(car.driverName), car.vehicleLabel),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.labelLarge,
                  ),
                ),
                if (car.rating case final rating? when rating > 0) ...[
                  Icon(
                    Icons.star_rounded,
                    size: 16,
                    color: theme.colorScheme.tertiary,
                  ),
                  Text(
                    formatRating(rating),
                    style: SoumTheme.tabular(theme.textTheme.labelMedium!),
                  ),
                ] else
                  Text(
                    strings.carNew,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.secondary,
                    ),
                  ),
                const SizedBox(width: 10),
                // «0 د» يقرأها الزبون «لن يأتي»؛ السيارة التي بجانبه دقيقة.
                Text(
                  strings.unitMinutes(car.etaMinutes < 1 ? 1 : car.etaMinutes),
                  style: SoumTheme.tabular(theme.textTheme.labelMedium!),
                ),
              ],
            ),
    );
  }
}

/// نطاق البحث: من خيارات المشغّل لكلّ منطقة. داخل المدينة ٥٠٠ متر
/// تكفي، وفي الضيعة لا تكفي عشرة كيلومترات أحيانًا.
class _RadiusPicker extends StatelessWidget {
  const _RadiusPicker({
    required this.options,
    required this.selected,
    required this.onSelect,
  });

  final List<double> options;
  final double? selected;
  final ValueChanged<double> onSelect;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(
              Icons.radar_rounded,
              size: 16,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: 6),
            Text(strings.searchRadiusLabel, style: theme.textTheme.labelMedium),
          ],
        ),
        const SizedBox(height: 6),
        // أجزاءٌ متساوية لا شريطٌ يُمرَّر: الخيار المختار يجب أن يُرى دائمًا.
        Row(
          children: [
            for (final km in options) ...[
              if (km != options.first) const SizedBox(width: 6),
              Expanded(
                child: ChoiceChip(
                  label: SizedBox(
                    width: double.infinity,
                    child: Text(
                      radiusLabel(strings, km),
                      textAlign: TextAlign.center,
                      maxLines: 1,
                    ),
                  ),
                  selected: km == selected,
                  showCheckmark: false,
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 2,
                    vertical: 6,
                  ),
                  onSelected: (_) => onSelect(km),
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

/// الرقم وحده بالكيلومتر: «0.5» أو «3» أو «1.5».
String radiusLabelNumber(double km) {
  if (km == km.roundToDouble()) return km.toStringAsFixed(0);
  return km.toStringAsFixed(1);
}

/// «500 م» أو «3 كم» أو «1.5 كم».
String radiusLabel(SoumStrings strings, double km) {
  if (km < 1) return strings.radiusMeters('${(km * 1000).round()}');
  final whole = km == km.roundToDouble();
  return strings.radiusKm(
    whole ? km.toStringAsFixed(0) : km.toStringAsFixed(1),
  );
}

/// درجة المزاد — عادي، اقتصادي، مشترك — حين تتيح المنطقة أكثر من واحدة.
class _ClassPicker extends StatelessWidget {
  const _ClassPicker({
    required this.modes,
    required this.selected,
    required this.onSelect,
  });

  final List<String> modes;
  final String? selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);

    return Wrap(
      spacing: 8,
      runSpacing: 6,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text(
          strings.serviceClass,
          style: Theme.of(context).textTheme.labelMedium,
        ),
        for (final mode in modes)
          ChoiceChip(
            // رمزٌ لا يعرفه التطبيق يُعرض كما هو: مشغّلٌ أضاف نمطًا جديدًا
            // يجب أن يراه المستخدم، ولو بلا اسم مترجم بعد.
            label: Text(switch (mode) {
              'standard' => strings.modeStandard,
              'saving' => strings.modeSaving,
              'shared' => strings.modeShared,
              'fast' => strings.modeFast,
              'express' => strings.modeExpress,
              _ => mode,
            }),
            selected: mode == selected,
            onSelected: (_) => onSelect(mode),
          ),
      ],
    );
  }
}

class _DestinationRow extends StatelessWidget {
  const _DestinationRow({required this.destination, required this.onPick});

  final GeoPoint? destination;
  final VoidCallback onPick;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return InkWell(
      onTap: onPick,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Icon(
              Icons.place_rounded,
              size: 20,
              color: theme.colorScheme.primary,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                destination == null
                    ? strings.homeWhereTo
                    : strings.homeDestination,
                style: destination == null
                    ? theme.textTheme.titleMedium
                    : theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
              ),
            ),
            Text(
              strings.homeSetOnMap,
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.tertiary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CategoryPicker extends StatelessWidget {
  const _CategoryPicker({
    required this.allowed,
    required this.selected,
    required this.onSelect,
  });

  /// من `trip_categories` في الإعداد — ما أطفأه المشغّل لا يظهر.
  final List<String> allowed;
  final TripCategory selected;
  final ValueChanged<TripCategory> onSelect;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);

    // الترفيهية غائبة عمدًا: تُحجز من كتالوج الرحلات المنشورة لا بطلب
    // جديد — والخادم يرفضها هنا صراحةً.
    const categories = [
      TripCategory.city,
      TripCategory.intercity,
      TripCategory.serviceLine,
    ];

    return Wrap(
      spacing: 8,
      children: [
        for (final category in categories)
          if (allowed.contains(category.code))
            ChoiceChip(
              label: Text(switch (category) {
                TripCategory.city => strings.categoryCity,
                TripCategory.intercity => strings.categoryIntercity,
                TripCategory.serviceLine => strings.categoryServiceLine,
                _ => category.code,
              }),
              selected: category == selected,
              onSelected: (_) => onSelect(category),
            ),
      ],
    );
  }
}

class _PassengerAndVehicle extends StatelessWidget {
  const _PassengerAndVehicle({
    required this.categories,
    required this.passengers,
    required this.vehicleType,
    required this.onPassengers,
    required this.onVehicle,
  });

  final List<VehicleCategoryOption> categories;
  final int passengers;
  final String? vehicleType;
  final ValueChanged<int> onPassengers;
  final ValueChanged<String?> onVehicle;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);

    // سعة الفئة المختارة تحدّ عدد الركّاب: الخادم يفلتر السائقين بالسعة
    // أصلًا، فطلبُ ستّة ركّاب بسيدان طلبٌ لن يجد سائقًا أبدًا.
    final maxSeats = vehicleType == null
        ? 8
        : categories
                  .where((c) => c.code == vehicleType)
                  .map((c) => c.seats)
                  .firstOrNull ??
              8;

    return Row(
      children: [
        Expanded(
          child: DropdownButtonFormField<int>(
            initialValue: passengers.clamp(1, maxSeats),
            isDense: true,
            decoration: const InputDecoration(isDense: true),
            items: [
              for (var count = 1; count <= maxSeats; count++)
                DropdownMenuItem(
                  value: count,
                  child: Text(strings.passengers(count)),
                ),
            ],
            onChanged: (value) => onPassengers(value ?? 1),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: DropdownButtonFormField<String?>(
            initialValue: vehicleType,
            isDense: true,
            decoration: const InputDecoration(isDense: true),
            items: [
              DropdownMenuItem(value: null, child: Text(strings.vehicleAny)),
              // من الإعداد لا من قائمة مكتوبة (§12.3).
              for (final category in categories)
                DropdownMenuItem(
                  value: category.code,
                  child: Text(category.name),
                ),
            ],
            onChanged: onVehicle,
          ),
        ),
      ],
    );
  }
}

class _RouteEstimate extends StatelessWidget {
  const _RouteEstimate({required this.route});

  final RouteResult route;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final isApproximate = route.source.isApproximate;

    return Row(
      children: [
        Icon(
          isApproximate ? Icons.straighten_rounded : Icons.route_rounded,
          size: 17,
          color: theme.colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 7),
        Text(
          strings.routeSummary(
            strings.unitKm(route.distanceKm.toStringAsFixed(1)),
            strings.unitMinutes(route.durationMinutes),
          ),
          style: SoumTheme.tabular(theme.textTheme.bodySmall!),
        ),
        const Spacer(),
        Text(
          isApproximate ? strings.fareApproximate : strings.fareRouted,
          style: theme.textTheme.labelSmall?.copyWith(
            color: isApproximate
                ? theme.colorScheme.tertiary
                : theme.colorScheme.secondary,
          ),
        ),
      ],
    );
  }
}

/// «الآن» أو موعد. رقاقتان لا حقل تاريخ: أغلب الطلبات الآن، والموعد
/// استثناءٌ يُفتح بضغطة.
class _WhenRow extends StatelessWidget {
  const _WhenRow({
    required this.scheduledAt,
    required this.onNow,
    required this.onPick,
  });

  final DateTime? scheduledAt;
  final VoidCallback onNow;
  final VoidCallback onPick;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final locale = Localizations.localeOf(context).toString();
    final when = scheduledAt;

    return Row(
      children: [
        ChoiceChip(
          label: Text(strings.scheduleNow),
          avatar: when == null
              ? null
              : Icon(
                  Icons.bolt_rounded,
                  size: 16,
                  color: Theme.of(context).colorScheme.onSurface,
                ),
          showCheckmark: when == null,
          selected: when == null,
          onSelected: (_) => onNow(),
        ),
        const SizedBox(width: 8),
        Flexible(
          child: ChoiceChip(
            label: Text(
              when == null
                  ? strings.scheduleLater
                  : DateFormat(strings.scheduleFormat, locale).format(when),
              overflow: TextOverflow.ellipsis,
            ),
            avatar: when != null
                ? null
                : Icon(
                    Icons.schedule_rounded,
                    size: 16,
                    color: Theme.of(context).colorScheme.onSurface,
                  ),
            showCheckmark: when != null,
            selected: when != null,
            onSelected: (_) => onPick(),
          ),
        ),
      ],
    );
  }
}
