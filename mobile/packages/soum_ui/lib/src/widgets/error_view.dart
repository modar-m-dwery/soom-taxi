/// عرض الخطأ — من `ApiException` مباشرةً.
///
/// قاعدتان من الدليل تحكمان هذا الملفّ:
///
/// > لا تقارن نصوصًا عربية — تفرّع على `code` وحده.
///
/// > سائق موقوف أو وثائقه منتهية — اعرض السبب من `detail` لا رسالة عامّة.
///
/// وهما معًا يعنيان: الرمز يقرّر الشكل والفعل، و`detail` هو النصّ. ورسالة
/// «حدث خطأ ما» ممنوعة حين يكون الخادم قد أرسل سببًا مكتوبًا بالعربية
/// جاهزًا للعرض.
///
/// و`request_id` يظهر للمستخدم لأنّه ما يحوّل شكوى «التطبيق لا يعمل» إلى
/// سطر واحد في سجلّ الخادم.
library;

import 'package:flutter/material.dart';
import 'package:soum_core/soum_core.dart';

import '../l10n/generated/soum_strings.dart';

class ApiErrorView extends StatelessWidget {
  const ApiErrorView({
    super.key,
    required this.failure,
    this.onRetry,
    this.compact = false,
  });

  final ApiException failure;
  final VoidCallback? onRetry;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    final title = failure.isNetwork ? strings.errorNetwork : strings.errorGeneric;
    final body = failure.isNetwork ? strings.errorNetworkBody : failure.detail;

    return Padding(
      padding: EdgeInsets.all(compact ? 16 : 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Icon(
            failure.isNetwork ? Icons.wifi_off_rounded : Icons.error_outline_rounded,
            size: compact ? 28 : 40,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 12),
          Text(
            title,
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text(
            body,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (failure.requestId != null) ...[
            const SizedBox(height: 10),
            Text(
              strings.errorSupportReference(failure.requestId!),
              textAlign: TextAlign.center,
              style: theme.textTheme.labelSmall,
            ),
          ],
          if (onRetry != null) ...[
            const SizedBox(height: 20),
            FilledButton(onPressed: onRetry, child: Text(strings.actionRetry)),
          ],
        ],
      ),
    );
  }
}

/// شريط خطأ قصير — لخطأ لا يُفرغ الشاشة، مثل 409 عند اختيار عرض.
void showApiError(BuildContext context, ApiException failure) {
  final strings = SoumStrings.of(context);

  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(
          failure.isNetwork ? strings.errorNetworkBody : failure.detail,
        ),
        duration: const Duration(seconds: 4),
      ),
    );
}
