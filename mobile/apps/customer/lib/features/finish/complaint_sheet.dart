/// الشكوى — نافذة ثلاثين يومًا.
///
/// §6.2 في وثيقة المنتج: نافذة الشكوى أطول من نافذة التقييم عمدًا، «لأنّ
/// المشكلة قد تتكشّف متأخّرة: خصم مالي، غرض منسيّ». ولذلك مدخلها من سجلّ
/// الرحلات لا من شاشة النهاية وحدها — الغرض المنسيّ يُكتشف في البيت لا
/// عند الباب.
///
/// والفئة تُرسل رمزًا لا نصًّا: التصنيف هو ما يوجّه الشكوى إلى من يعالجها،
/// ونصٌّ حرّ يجعل كلّ شكوى تمرّ بقارئ بشريّ قبل أن تُصنَّف.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

Future<void> showComplaintSheet(BuildContext context, int rideId) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: _ComplaintSheet(rideId: rideId),
    ),
  );
}

class _ComplaintSheet extends ConsumerStatefulWidget {
  const _ComplaintSheet({required this.rideId});

  final int rideId;

  @override
  ConsumerState<_ComplaintSheet> createState() => _ComplaintSheetState();
}

class _ComplaintSheetState extends ConsumerState<_ComplaintSheet> {
  static const _categories = [
    'fare',
    'driver_conduct',
    'safety',
    'lost_item',
    'other',
  ];

  String _category = 'fare';
  final _description = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    String label(String code) => switch (code) {
          'fare' => strings.complaintCatFare,
          'driver_conduct' => strings.complaintCatDriver,
          'safety' => strings.complaintCatSafety,
          'lost_item' => strings.complaintCatLostItem,
          _ => strings.complaintCatOther,
        };

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
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
            Text(strings.complaintOpen, style: theme.textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(strings.complaintWindow, style: theme.textTheme.bodySmall),

            const SizedBox(height: 16),
            Text(strings.complaintCategory, style: theme.textTheme.labelMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 7,
              runSpacing: 7,
              children: [
                for (final code in _categories)
                  ChoiceChip(
                    label: Text(label(code)),
                    selected: code == _category,
                    onSelected: (_) => setState(() => _category = code),
                  ),
              ],
            ),

            const SizedBox(height: 14),
            TextField(
              controller: _description,
              maxLines: 4,
              autofocus: true,
              decoration: InputDecoration(
                labelText: strings.complaintDescription,
              ),
              onChanged: (_) => setState(() {}),
            ),

            const SizedBox(height: 16),
            FilledButton(
              onPressed: _description.text.trim().length >= 10 && !_sending
                  ? _submit
                  : null,
              child: _sending
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    )
                  : Text(strings.complaintSubmit),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _submit() async {
    setState(() => _sending = true);

    try {
      await ref.read(soumProvider).feedback.openComplaint(
            rideId: widget.rideId,
            category: _category,
            description: _description.text.trim(),
          );

      if (!mounted) return;
      final strings = SoumStrings.of(context);
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(strings.complaintSent)));
    } on ApiException catch (error) {
      if (!mounted) return;
      // نصّ الخادم لا رسالة عامّة: خارج نافذة الثلاثين يومًا يقول السبب.
      showApiError(context, error);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }
}
