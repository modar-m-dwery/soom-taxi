import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// زرّ اتّصال بالطرف الآخر. يفتح لوحة الاتّصال لا يتّصل مباشرةً: لا حاجة
/// لإذن CALL_PHONE، والمستخدم يرى الرقم قبل أن يضغط.
class CallButton extends StatelessWidget {
  const CallButton({super.key, required this.phone, required this.tooltip});

  final String? phone;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    final number = phone;
    if (number == null || number.isEmpty) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    return IconButton.filled(
      tooltip: tooltip,
      style: IconButton.styleFrom(
        backgroundColor: scheme.secondary,
        foregroundColor: scheme.onSecondary,
      ),
      icon: const Icon(Icons.call_rounded),
      onPressed: () => launchUrl(Uri(scheme: 'tel', path: number)),
    );
  }
}
