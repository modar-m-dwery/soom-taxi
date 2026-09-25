/// التوثيق — خطوات مرتّبة كما يفرضها الخادم.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
// intl يصدّر TextDirection بأسماء LTR/RTL، وهو يحجب نظيره في dart:ui.
// إخفاؤه هنا أوضح من تسمية الاستيراد كلّه.
import 'package:intl/intl.dart' hide TextDirection;
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import 'onboarding_controller.dart';

class OnboardingScreen extends ConsumerWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final state = ref.watch(onboardingControllerProvider);

    return Scaffold(
      appBar: AppBar(title: Text(strings.onboardTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _Step(
            index: 1,
            label: strings.onboardBecomeDriver,
            isDone: state.step != OnboardingStep.becomeDriver,
            child: state.step == OnboardingStep.becomeDriver
                ? FilledButton(
                    onPressed: state.isBusy
                        ? null
                        : () => ref
                            .read(onboardingControllerProvider.notifier)
                            .becomeDriver(),
                    child: Text(strings.onboardBecomeDriver),
                  )
                : null,
          ),

          _Step(
            index: 2,
            label: strings.onboardAddVehicle,
            isDone: state.hasActiveVehicle,
            child: state.step == OnboardingStep.vehicle
                ? const VehicleForm()
                : null,
          ),

          _Step(
            index: 3,
            label: strings.onboardDocuments,
            isDone: state.allApproved,
            child: state.step == OnboardingStep.documents ||
                    state.step == OnboardingStep.review
                ? const DocumentList()
                : null,
          ),

          if (state.step == OnboardingStep.review) ...[
            const SizedBox(height: 18),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: theme.colorScheme.tertiary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  Icon(Icons.hourglass_top_rounded,
                      size: 19, color: theme.colorScheme.tertiary),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(strings.onboardPendingReview,
                        style: theme.textTheme.bodyMedium),
                  ),
                ],
              ),
            ),
          ],

          if (state.failure != null) ...[
            const SizedBox(height: 16),
            ApiErrorView(failure: state.failure!, compact: true),
          ],
        ],
      ),
    );
  }
}

class _Step extends StatelessWidget {
  const _Step({
    required this.index,
    required this.label,
    required this.isDone,
    this.child,
  });

  final int index;
  final String label;
  final bool isDone;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 15,
                backgroundColor: isDone
                    ? theme.colorScheme.secondary
                    : theme.colorScheme.surfaceContainerHighest,
                child: isDone
                    ? Icon(Icons.check_rounded,
                        size: 17, color: theme.colorScheme.onSecondary)
                    : Text('$index', style: theme.textTheme.labelLarge),
              ),
              const SizedBox(width: 12),
              Expanded(child: Text(label, style: theme.textTheme.titleMedium)),
              if (isDone)
                Text(strings.onboardStepDone,
                    style: theme.textTheme.labelSmall),
            ],
          ),
          if (child != null) ...[
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsetsDirectional.only(start: 42),
              child: child,
            ),
          ],
        ],
      ),
    );
  }
}

class VehicleForm extends ConsumerStatefulWidget {
  const VehicleForm({super.key});

  @override
  ConsumerState<VehicleForm> createState() => _VehicleFormState();
}

class _VehicleFormState extends ConsumerState<VehicleForm> {
  final _make = TextEditingController();
  final _model = TextEditingController();
  final _year = TextEditingController(text: '2015');
  final _color = TextEditingController();
  final _plate = TextEditingController();
  String? _type;
  int _seats = 4;

  @override
  void dispose() {
    for (final controller in [_make, _model, _year, _color, _plate]) {
      controller.dispose();
    }
    super.dispose();
  }

  bool get _isValid =>
      _type != null &&
      _make.text.trim().isNotEmpty &&
      _model.text.trim().isNotEmpty &&
      _plate.text.trim().isNotEmpty &&
      (int.tryParse(_year.text) ?? 0) > 1950;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final config = ref.watch(configProvider);
    final state = ref.watch(onboardingControllerProvider);

    // §12.3: «فئات المركبات تُبنى من vehicle_categories لا من قائمة
    // مكتوبة في التطبيق». مشغّلٌ يضيف «تكتك» بصفّ واحد يجب أن يراه
    // السائق فورًا.
    final categories = config.vehicleCategories;
    _type ??= categories.isEmpty ? null : categories.first.code;

    final seatsCap = categories
            .where((c) => c.code == _type)
            .map((c) => c.seats)
            .firstOrNull ??
        8;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _type,
          decoration: InputDecoration(labelText: strings.vehicleType),
          items: [
            for (final category in categories)
              DropdownMenuItem(
                value: category.code,
                child: Text(category.name),
              ),
          ],
          onChanged: (value) => setState(() {
            _type = value;
            _seats = _seats.clamp(1, seatsCap);
          }),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _make,
                decoration: InputDecoration(labelText: strings.vehicleMake),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                controller: _model,
                decoration: InputDecoration(labelText: strings.vehicleModel),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _year,
                keyboardType: TextInputType.number,
                textDirection: TextDirection.ltr,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: InputDecoration(labelText: strings.vehicleYear),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                controller: _color,
                decoration: InputDecoration(labelText: strings.vehicleColor),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _plate,
          textDirection: TextDirection.ltr,
          decoration: InputDecoration(labelText: strings.vehiclePlate),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 10),
        DropdownButtonFormField<int>(
          initialValue: _seats.clamp(1, seatsCap),
          decoration: InputDecoration(labelText: strings.vehicleSeats),
          items: [
            for (var count = 1; count <= seatsCap; count++)
              DropdownMenuItem(value: count, child: Text('$count')),
          ],
          onChanged: (value) => setState(() => _seats = value ?? 4),
        ),
        const SizedBox(height: 14),
        FilledButton(
          onPressed: _isValid && !state.isBusy ? _submit : null,
          child: Text(strings.vehicleAdd),
        ),
      ],
    );
  }

  Future<void> _submit() async {
    final ok = await ref
        .read(onboardingControllerProvider.notifier)
        .registerVehicle(
          type: _type!,
          make: _make.text.trim(),
          model: _model.text.trim(),
          year: int.parse(_year.text),
          color: _color.text.trim(),
          plateNumber: _plate.text.trim(),
          seats: _seats,
        );

    if (!mounted || !ok) return;
    final strings = SoumStrings.of(context);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(strings.vehicleSaved)));
  }
}

class DocumentList extends ConsumerWidget {
  const DocumentList({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(onboardingControllerProvider);
    final byType = state.byType;

    return Column(
      children: [
        // من التعداد لا من المرفوع: أربع وثائق مطلوبة دائمًا، وعرض ما
        // رُفع وحده يُخفي ما ينقص.
        for (final type in DriverDocumentType.values)
          _DocumentRow(type: type, document: byType[type]),
      ],
    );
  }
}

class _DocumentRow extends ConsumerStatefulWidget {
  const _DocumentRow({required this.type, required this.document});

  final DriverDocumentType type;
  final DriverDocument? document;

  @override
  ConsumerState<_DocumentRow> createState() => _DocumentRowState();
}

class _DocumentRowState extends ConsumerState<_DocumentRow> {
  bool _uploading = false;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final document = widget.document;
    final locale = Localizations.localeOf(context).toString();

    final label = switch (widget.type) {
      DriverDocumentType.nationalId => strings.docNationalId,
      DriverDocumentType.driverLicense => strings.docDriverLicense,
      DriverDocumentType.vehicleRegistration => strings.docVehicleRegistration,
      DriverDocumentType.insurance => strings.docInsurance,
    };

    final (statusLabel, statusColor) = switch (document?.status) {
      DocumentStatus.approved when document!.isExpired => (
          strings.docExpired,
          theme.colorScheme.error,
        ),
      DocumentStatus.approved => (
          strings.docApproved,
          theme.colorScheme.secondary,
        ),
      DocumentStatus.pending => (strings.docPending, theme.colorScheme.tertiary),
      DocumentStatus.rejected => (strings.docRejected, theme.colorScheme.error),
      DocumentStatus.expired => (strings.docExpired, theme.colorScheme.error),
      _ => ('', theme.colorScheme.outline),
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: theme.textTheme.titleMedium),
                if (statusLabel.isNotEmpty)
                  Text(
                    statusLabel,
                    style: theme.textTheme.labelSmall?.copyWith(color: statusColor),
                  ),
                if (document?.expiresAt != null)
                  Text(
                    strings.docExpiresOn(
                      DateFormat.yMMMd(locale).format(document!.expiresAt!),
                    ),
                    style: SoumTheme.tabular(theme.textTheme.labelSmall!),
                  ),
                // سببُ الرفض من الخادم: «ارفع مرّة أخرى» بلا سبب يجعل
                // السائق يرفع الصورة نفسها.
                if (document?.status == DocumentStatus.rejected &&
                    document!.rejectionReason.isNotEmpty)
                  Text(
                    document.rejectionReason,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.error),
                  ),
              ],
            ),
          ),
          TextButton(
            onPressed: _uploading ? null : _pick,
            child: Text(
              _uploading
                  ? strings.docUploading
                  : document == null
                      ? strings.docUpload
                      : strings.docReplace,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _pick() async {
    final picker = ImagePicker();
    final file = await picker.pickImage(
      source: ImageSource.camera,
      // ضغطٌ قبل الرفع: صورة كاملة من كاميرا حديثة تتجاوز عشرة ميغابايت،
      // ورفعُها على شبكة هاتف بطيئة هو ما يجعل السائق يستسلم عند الوثيقة
      // الثالثة.
      imageQuality: 78,
      maxWidth: 2000,
    );
    if (file == null) return;

    setState(() => _uploading = true);
    await ref.read(onboardingControllerProvider.notifier).uploadDocument(
          type: widget.type,
          filePath: file.path,
        );
    if (mounted) setState(() => _uploading = false);
  }
}
