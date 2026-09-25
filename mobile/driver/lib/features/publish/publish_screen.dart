/// نشر رحلة — سفريّة أو سرفيس أو رحلة ترفيهية.
///
/// امتدادٌ لنموذج المنصّة لا ميزةٌ منفصلة: السائق ينشر مقاعد بسعر وموعد،
/// والزبون يحجز مقعدًا من الكتالوج. ولذلك `trip_category` هنا ثلاثة
/// خيارات لا أربعة — «داخل المدينة» ليست رحلةً تُنشَر.
///
/// وبين‑المدن وخطّ السرفيس يفرضان مدينتَي الانطلاق والوصول، تمامًا كما
/// في إنشاء الطلب. الخادم يرفض بدونهما، فنفرضهما في النموذج.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import '../onboarding/onboarding_controller.dart';

class PublishScreen extends ConsumerStatefulWidget {
  const PublishScreen({super.key});

  @override
  ConsumerState<PublishScreen> createState() => _PublishScreenState();
}

class _PublishScreenState extends ConsumerState<PublishScreen> {
  final _title = TextEditingController();
  final _originCity = TextEditingController();
  final _destinationCity = TextEditingController();
  final _price = TextEditingController();

  TripCategory _category = TripCategory.intercity;
  int _capacity = 4;
  DateTime _when = DateTime.now().add(const Duration(hours: 2));
  GeoPoint? _pickup;
  GeoPoint? _destination;
  bool _sending = false;
  ApiException? _failure;

  @override
  void dispose() {
    for (final controller in [
      _title,
      _originCity,
      _destinationCity,
      _price,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  bool get _isValid {
    if (_capacity < 1 || _sending) return false;
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
    final onboarding = ref.watch(onboardingControllerProvider);
    final vehicle = onboarding.vehicles.where((v) => v.active).firstOrNull;

    return Scaffold(
      appBar: AppBar(title: Text(strings.publishTitle)),
      body: vehicle == null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  strings.onboardAddVehicle,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Wrap(
                  spacing: 8,
                  children: [
                    for (final category in const [
                      TripCategory.intercity,
                      TripCategory.serviceLine,
                      TripCategory.recreational,
                    ])
                      ChoiceChip(
                        label: Text(switch (category) {
                          TripCategory.intercity => strings.categoryIntercity,
                          TripCategory.serviceLine =>
                            strings.categoryServiceLine,
                          _ => strings.categoryRecreational,
                        }),
                        selected: category == _category,
                        onSelected: (_) => setState(() => _category = category),
                      ),
                  ],
                ),

                const SizedBox(height: 14),
                TextField(
                  controller: _title,
                  decoration: InputDecoration(
                    labelText: strings.publishTitleField,
                  ),
                ),

                if (_category.requiresCities) ...[
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _originCity,
                          decoration:
                              InputDecoration(labelText: strings.cityOrigin),
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TextField(
                          controller: _destinationCity,
                          decoration: InputDecoration(
                            labelText: strings.cityDestination,
                          ),
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                    ],
                  ),
                ],

                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<int>(
                        initialValue: _capacity.clamp(1, vehicle.seats),
                        decoration:
                            InputDecoration(labelText: strings.publishCapacity),
                        items: [
                          // السعة مقيَّدة بمقاعد المركبة: نشرُ ثمانية
                          // مقاعد بسيدان يَعِد بما لا يمكن الوفاء به.
                          for (var count = 1; count <= vehicle.seats; count++)
                            DropdownMenuItem(
                              value: count,
                              child: Text('$count'),
                            ),
                        ],
                        onChanged: (value) =>
                            setState(() => _capacity = value ?? 1),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: _price,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        textDirection: TextDirection.ltr,
                        inputFormatters: [
                          FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
                        ],
                        style: SoumTheme.tabular(theme.textTheme.bodyLarge!),
                        decoration: InputDecoration(
                          labelText: strings.publishPricePerSeat,
                          suffixText: strings.currencySyp,
                        ),
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(strings.publishWhen),
                  subtitle: Text(
                    _when.toLocal().toString().substring(0, 16),
                    textDirection: TextDirection.ltr,
                  ),
                  trailing: const Icon(Icons.schedule_rounded),
                  onTap: _pickWhen,
                ),

                if (_failure != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    _failure!.detail,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.error),
                  ),
                ],

                const SizedBox(height: 18),
                FilledButton(
                  onPressed: _isValid ? () => _submit(vehicle) : null,
                  child: _sending
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2.2),
                        )
                      : Text(strings.publishSubmit),
                ),
              ],
            ),
    );
  }

  Future<void> _pickWhen() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _when,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 60)),
    );
    if (date == null || !mounted) return;

    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_when),
    );
    if (time == null) return;

    setState(() {
      _when = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
    });
  }

  Future<void> _submit(Vehicle vehicle) async {
    final config = ref.read(configProvider);
    setState(() {
      _sending = true;
      _failure = null;
    });

    try {
      // نقطتا الانطلاق والوصول: الموقع الحالي للسائق نقطةَ انطلاق،
      // والوجهة من الخريطة في نسخة لاحقة. المدينتان نصًّا هما ما يفلتر
      // به الكتالوج فعلًا في رحلات بين‑المدن.
      await ref.read(soumProvider).sharing.publishTrip(
            vehicleId: vehicle.id,
            tripCategory: _category.code,
            scheduledAt: _when,
            capacity: _capacity,
            pickup: _pickup ?? const GeoPoint(35.3608, 35.9236),
            destination: _destination ?? const GeoPoint(35.5300, 35.7800),
            originCity:
                _category.requiresCities ? _originCity.text.trim() : null,
            destinationCity:
                _category.requiresCities ? _destinationCity.text.trim() : null,
            pricePerSeat: _price.text.trim().isEmpty
                ? null
                : Money.parse(
                    _price.text.trim(),
                    config.pricing.currencyCode,
                  ),
            title: _title.text.trim().isEmpty ? null : _title.text.trim(),
          );

      if (!mounted) return;
      final strings = SoumStrings.of(context);
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(strings.publishDone)));
    } on ApiException catch (error) {
      if (mounted) setState(() => _failure = error);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }
}
