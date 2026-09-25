/// نهاية الرحلة — الدفع ثمّ التقييم.
///
/// قيدٌ أمنيّ يصمّم هذه الشاشة كاملةً (§6.3):
///
/// > في الدفع النقدي، السائق وحده — أو الإدارة — من يؤكّد القبض. زر
/// > «دفعت» في تطبيق الزبون يردّ 403. اعرض للزبون «بانتظار تأكيد السائق»،
/// > وضع زرّ التأكيد في تطبيق السائق.
///
/// لذلك: **لا زرّ تأكيد قبض في هذا الملفّ إطلاقًا**. وهو بندٌ يُفحص آليًّا
/// في اختبارات M6.
///
/// والتقييم: تحت ثلاث نجوم يصير السبب إلزاميًّا — «نجمة بلا سبب لا تُصلح
/// شيئًا ولا تدخل في أيّ قرار».
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import '../ride/ride_controller.dart';
import '../home/ad_banner.dart';
import 'complaint_sheet.dart';

class FinishScreen extends ConsumerStatefulWidget {
  const FinishScreen({super.key});

  @override
  ConsumerState<FinishScreen> createState() => _FinishScreenState();
}

class _FinishScreenState extends ConsumerState<FinishScreen> {
  int _rating = 0;
  final _selectedTags = <String>{};
  final _comment = TextEditingController();
  List<RatingTag> _tags = const [];
  bool _submitting = false;
  bool _rated = false;

  @override
  void initState() {
    super.initState();
    _loadTags();
  }

  @override
  void dispose() {
    _comment.dispose();
    super.dispose();
  }

  Future<void> _loadTags() async {
    try {
      final tags = await ref.read(soumProvider).feedback.tags();
      if (mounted) setState(() => _tags = tags);
    } on ApiException {
      // بلا وسوم يبقى التعليق سبيلًا كافيًا للسبب الإلزاميّ.
    }
  }

  /// §6.2 — تحت ثلاث نجوم يلزم وسم أو تعليق.
  bool get _needsReason => _rating > 0 && _rating < 3;

  bool get _canSubmit {
    if (_rating == 0 || _submitting || _rated) return false;
    if (!_needsReason) return true;
    return _selectedTags.isNotEmpty || _comment.text.trim().isNotEmpty;
  }

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final arc = ref.watch(rideControllerProvider);
    final payment = arc.pendingPayment;

    return Scaffold(
      appBar: AppBar(title: Text(strings.tripCompleted)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (payment != null) _PaymentCard(payment: payment),
          const SizedBox(height: 12),
          // مكان إعلان بعد الوصول — لحظةٌ هادئة لا يُقاطَع فيها طلب.
          const AdBanner(placement: 'trip_finished', height: 96),
          const SizedBox(height: 18),

          Text(strings.rateTitle, style: theme.textTheme.titleLarge),
          const SizedBox(height: 12),
          _Stars(
            value: _rating,
            onChanged: (value) => setState(() => _rating = value),
          ),

          if (_needsReason) ...[
            const SizedBox(height: 14),
            Text(strings.rateReasonRequired, style: theme.textTheme.bodySmall),
            const SizedBox(height: 8),
            Wrap(
              spacing: 7,
              runSpacing: 7,
              children: [
                for (final tag in _tags.where((t) => t.isNegative))
                  FilterChip(
                    label: Text(tag.label),
                    selected: _selectedTags.contains(tag.code),
                    onSelected: (selected) => setState(() {
                      if (selected) {
                        _selectedTags.add(tag.code);
                      } else {
                        _selectedTags.remove(tag.code);
                      }
                    }),
                  ),
              ],
            ),
          ] else if (_rating >= 4) ...[
            const SizedBox(height: 14),
            Wrap(
              spacing: 7,
              runSpacing: 7,
              children: [
                for (final tag in _tags.where((t) => !t.isNegative))
                  FilterChip(
                    label: Text(tag.label),
                    selected: _selectedTags.contains(tag.code),
                    onSelected: (selected) => setState(() {
                      if (selected) {
                        _selectedTags.add(tag.code);
                      } else {
                        _selectedTags.remove(tag.code);
                      }
                    }),
                  ),
              ],
            ),
          ],

          const SizedBox(height: 14),
          TextField(
            controller: _comment,
            maxLines: 3,
            decoration: InputDecoration(labelText: strings.rateComment),
            onChanged: (_) => setState(() {}),
          ),

          const SizedBox(height: 18),
          FilledButton(
            onPressed: _canSubmit ? _submit : null,
            child: Text(_rated ? strings.rateThanks : strings.rateSubmit),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              TextButton(
                onPressed: () =>
                    ref.read(rideControllerProvider.notifier).leaveFinished(),
                child: Text(strings.skip),
              ),
              TextButton.icon(
                onPressed: () {
                  final rideId = arc.ride?.id ??
                      arc.trip?.rideId ??
                      arc.pendingPayment?.rideId;
                  if (rideId != null) showComplaintSheet(context, rideId);
                },
                icon: const Icon(Icons.flag_outlined, size: 17),
                label: Text(strings.complaintOpen),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _submit() async {
    final arc = ref.read(rideControllerProvider);
    final rideId = arc.ride?.id ?? arc.trip?.rideId ?? arc.pendingPayment?.rideId;
    if (rideId == null) return;

    setState(() => _submitting = true);

    try {
      await ref.read(soumProvider).feedback.rate(
            rideId: rideId,
            rating: _rating,
            tags: _selectedTags.toList(),
            comment: _comment.text.trim().isEmpty ? null : _comment.text.trim(),
          );
      if (mounted) setState(() => _rated = true);
      // §5 في الدليل: بعد التقييم العودة إلى الرئيسية والرحلة في السجلّ.
      await ref.read(rideControllerProvider.notifier).leaveFinished();
    } on ApiException catch (error) {
      if (!mounted) return;

      final strings = SoumStrings.of(context);
      final message = error.code == ApiErrorCode.ratingDuplicate
          ? strings.rateAlready
          : error.detail;

      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(message)));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }
}

class _PaymentCard extends StatelessWidget {
  const _PaymentCard({required this.payment});

  final Payment payment;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final waiting = payment.awaitingDriverConfirmation;
    final hasDiscount = !payment.discountAmount.isZero;
    final discountStyle = theme.textTheme.bodyMedium?.copyWith(
      color: theme.colorScheme.secondary,
      fontWeight: FontWeight.w600,
    );

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // الخصم يُعرض كسطرين قبل الإجماليّ: «الأجرة» ثمّ «خصم أوّل
            // مشوار» أو «رصيد الدعوات». الزبون يرى ما وفّر، والسائق يرى
            // في تطبيقه أجرته كاملة — الفرق على المنصّة لا عليه.
            if (hasDiscount) ...[
              _Line(
                label: strings.paymentSubtotal,
                value: MoneyText(payment.amount + payment.discountAmount,
                    style: theme.textTheme.bodyMedium),
              ),
              _Line(
                label: payment.discountReason == 'credit'
                    ? strings.paymentDiscountCredit
                    : strings.paymentDiscountFirstRide,
                icon: Icons.local_offer_rounded,
                color: theme.colorScheme.secondary,
                value: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('− ', style: discountStyle),
                    MoneyText(payment.discountAmount, style: discountStyle),
                  ],
                ),
              ),
              const Divider(height: 18),
            ],
            Row(
              children: [
                Text(strings.paymentAmount, style: theme.textTheme.bodyMedium),
                const Spacer(),
                MoneyText(payment.amount, style: theme.textTheme.displaySmall),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: (waiting
                        ? theme.colorScheme.tertiary
                        : theme.colorScheme.secondary)
                    .withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Icon(
                    waiting
                        ? Icons.hourglass_top_rounded
                        : Icons.check_circle_rounded,
                    size: 19,
                    color: waiting
                        ? theme.colorScheme.tertiary
                        : theme.colorScheme.secondary,
                  ),
                  const SizedBox(width: 9),
                  Expanded(
                    child: Text(
                      waiting
                          ? strings.paymentCashWaiting
                          : strings.paymentPaid,
                      style: theme.textTheme.bodyMedium,
                    ),
                  ),
                ],
              ),
            ),
            if (waiting) ...[
              const SizedBox(height: 8),
              // لا زرّ هنا. القيد الأمنيّ ليس اقتراحًا: الزبون لا يستطيع
              // تأكيد قبض مالٍ لم يُقبَض، والخادم يردّ 403.
              Text(strings.paymentCashNote, style: theme.textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({
    required this.label,
    required this.value,
    this.icon,
    this.color,
  });

  final String label;
  final Widget value;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 6),
          ],
          Text(label,
              style: theme.textTheme.bodyMedium?.copyWith(color: color)),
          const Spacer(),
          value,
        ],
      ),
    );
  }
}

class _Stars extends StatelessWidget {
  const _Stars({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        for (var star = 1; star <= 5; star++)
          IconButton(
            iconSize: 36,
            onPressed: () => onChanged(star),
            icon: Icon(
              star <= value ? Icons.star_rounded : Icons.star_outline_rounded,
              color: star <= value ? scheme.primary : scheme.outline,
            ),
          ),
      ],
    );
  }
}
