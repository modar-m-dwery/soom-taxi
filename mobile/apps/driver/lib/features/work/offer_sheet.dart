/// بطاقة تقديم العرض.
///
/// السعر يُدخَل ضمن ممرّ `fare_floor…fare_cap` الذي يرسله الخادم مع الطلب.
/// الفحص محلّيّ **وأيضًا** على الخادم: المحلّي يمنع ضغطةً سترتدّ، والخادم
/// هو القرار. إسقاط أحدهما خطأ — الأوّل تجربة رديئة، والثاني ثغرة.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

import 'work_controller.dart';

Future<void> showOfferSheet(BuildContext context, RideRequest ride) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: _OfferSheet(ride: ride),
    ),
  );
}

class _OfferSheet extends ConsumerStatefulWidget {
  const _OfferSheet({required this.ride});

  final RideRequest ride;

  @override
  ConsumerState<_OfferSheet> createState() => _OfferSheetState();
}

class _OfferSheetState extends ConsumerState<_OfferSheet> {
  late final TextEditingController _fare;
  late final TextEditingController _eta;

  @override
  void initState() {
    super.initState();
    // السعر المرجعيّ الذي حسبه الخادم هو الافتراض: أكثرُ العروض تقبله
    // كما هو، وإجبارُ السائق على كتابته في كلّ طلب إبطاءٌ بلا فائدة.
    _fare = TextEditingController(text: widget.ride.fare.grossFare.toApi());
    _eta = TextEditingController(text: '5');
  }

  @override
  void dispose() {
    _fare.dispose();
    _eta.dispose();
    super.dispose();
  }

  Money? get _parsedFare {
    try {
      final value = Money.parse(_fare.text.trim(), widget.ride.fare.currency);
      return value.isZero ? null : value;
    } on FormatException {
      return null;
    }
  }

  /// null = ضمن الممرّ أو لا ممرّ.
  bool get _outOfRange {
    final fare = _parsedFare;
    final floor = widget.ride.fare.fareFloor;
    final cap = widget.ride.fare.fareCap;
    if (fare == null) return false;
    if (floor != null && fare < floor) return true;
    if (cap != null && fare > cap) return true;
    return false;
  }

  int? get _parsedEta => int.tryParse(_eta.text.trim());

  bool get _canSend =>
      _parsedFare != null &&
      !_outOfRange &&
      (_parsedEta ?? 0) > 0 &&
      !ref.read(workControllerProvider).isBusy;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final work = ref.watch(workControllerProvider);
    final fare = widget.ride.fare;

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
            Text(strings.workOfferTitle, style: theme.textTheme.titleLarge),

            if (fare.fareFloor != null && fare.fareCap != null) ...[
              const SizedBox(height: 4),
              Text(
                strings.workFareRange(
                  fare.fareFloor!.format(),
                  fare.fareCap!.format(),
                ),
                style: SoumTheme.tabular(theme.textTheme.bodySmall!),
              ),
            ],

            const SizedBox(height: 16),
            TextField(
              controller: _fare,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              textDirection: TextDirection.ltr,
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
              ],
              style: SoumTheme.tabular(theme.textTheme.titleLarge!),
              decoration: InputDecoration(
                labelText: strings.workOfferPrice,
                suffixText: strings.currencySyp,
                errorText: _outOfRange ? strings.workFareOutOfRange : null,
              ),
              onChanged: (_) => setState(() {}),
            ),

            const SizedBox(height: 12),
            TextField(
              controller: _eta,
              keyboardType: TextInputType.number,
              textDirection: TextDirection.ltr,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              style: SoumTheme.tabular(theme.textTheme.titleMedium!),
              decoration: InputDecoration(labelText: strings.workOfferEta),
              onChanged: (_) => setState(() {}),
            ),

            if (work.failure != null) ...[
              const SizedBox(height: 12),
              Text(
                // نصّ الخادم: يقول السبب الدقيق حين يرفض.
                work.failure!.detail,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            ],

            const SizedBox(height: 18),
            FilledButton(
              onPressed: _canSend ? _send : null,
              child: work.isBusy
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    )
                  : Text(strings.workOfferSend),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _send() async {
    final ok = await ref.read(workControllerProvider.notifier).submitOffer(
          rideId: widget.ride.id,
          fare: _parsedFare!,
          etaMinutes: _parsedEta!,
        );

    if (!mounted || !ok) return;

    final strings = SoumStrings.of(context);
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(strings.workOfferSent)));
  }
}
