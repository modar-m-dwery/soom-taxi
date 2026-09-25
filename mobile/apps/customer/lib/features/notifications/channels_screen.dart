/// قنوات الإيصال وربط تليغرام.
///
/// §10.1: «الخادم يمشي في سلسلة قنوات مرتَّبة، وأوّل قناة تُسلّم توقف
/// السلسلة — فالإشعار الواحد يصل مرّة واحدة لا ثلاثًا». والمستخدم يرتّبها.
///
/// وقاعدتان من §12.3 مطبَّقتان هنا حرفيًّا:
///
///   **قناة `configured: false` لا تظهر أصلًا** — لا معطَّلة ولا رمادية.
///   المشغّل لم يشترك بها على الخادم، فعرضُها يَعِد بما لا وجود له.
///
///   **503 على نقطة الربط ليست عطلًا** — تعني أنّ المشغّل لم يفعّل
///   تليغرام. نُخفي الخيار عندها بدل أن نعرض خطأ.
///
/// وقيد تليغرام نفسه يفسّر شكل الربط: البوت **لا يستطيع بدء محادثة**.
/// فالربط دورةٌ لا نداء: رمزٌ لمرّة واحدة، ورابط عميق، ثمّ ويب هوك يصل
/// الخادم حين يضغط المستخدم «ابدأ».
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';
import 'package:url_launcher/url_launcher.dart';

final channelsProvider =
    FutureProvider.autoDispose<List<NotificationChannel>>(
  (ref) => ref.read(soumProvider).notifications.channels(),
);

class ChannelsScreen extends ConsumerWidget {
  const ChannelsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final channels = ref.watch(channelsProvider);

    return Scaffold(
      appBar: AppBar(title: Text(strings.channelsTitle)),
      body: channels.when(
        loading: () =>
            const Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
        error: (error, _) => Center(
          child: ApiErrorView(
            failure: error is ApiException
                ? error
                : ApiException(
                    statusCode: 0,
                    code: ApiErrorCode.networkUnavailable,
                    detail: '$error',
                  ),
            onRetry: () => ref.invalidate(channelsProvider),
          ),
        ),
        data: (rows) {
          // الترشيح على `configured` لا على `enabled`: قناةٌ لم يشترك
          // بها المشغّل لا وجود لها من نظر المستخدم.
          final visible = rows.where((c) => c.isVisible).toList()
            ..sort((a, b) => a.priority.compareTo(b.priority));

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(strings.channelsHint, style: theme.textTheme.bodySmall),
              const SizedBox(height: 16),
              for (final channel in visible)
                _ChannelTile(channel: channel),
            ],
          );
        },
      ),
    );
  }
}

class _ChannelTile extends ConsumerStatefulWidget {
  const _ChannelTile({required this.channel});

  final NotificationChannel channel;

  @override
  ConsumerState<_ChannelTile> createState() => _ChannelTileState();
}

class _ChannelTileState extends ConsumerState<_ChannelTile> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final channel = widget.channel;

    final label = switch (channel.code) {
      'push' => strings.channelPush,
      'telegram' => strings.channelTelegram,
      'sms' => strings.channelSms,
      // رمزٌ لم يعرفه هذا الإصدار يُعرض باسمه من الخادم: قناةٌ رابعة
      // تُضاف غدًا يجب أن يراها المستخدم بلا تحديث من المتجر.
      _ => channel.label,
    };

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(label, style: theme.textTheme.titleMedium),
                      if (channel.requiresLinking)
                        Text(
                          channel.isLinked
                              ? strings.channelLinked
                              : strings.channelNotLinked,
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: channel.isLinked
                                ? theme.colorScheme.secondary
                                : theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                    ],
                  ),
                ),
                Switch(
                  // قناةٌ تحتاج ربطًا ولم تُربط لا تُفعَّل: التفعيل بلا
                  // ربط يجعل الخادم يجرّبها ويفشل، فيتأخّر الإشعار إلى
                  // القناة التالية بلا سبب.
                  value: channel.isEnabled,
                  onChanged: _busy ||
                          (channel.requiresLinking && !channel.isLinked)
                      ? null
                      : (value) => _toggle(value),
                ),
              ],
            ),

            if (channel.requiresLinking) ...[
              const SizedBox(height: 8),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: TextButton(
                  onPressed: _busy ? null : _link,
                  child: Text(
                    channel.isLinked
                        ? strings.channelUnlink
                        : strings.channelLink,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _toggle(bool enabled) async {
    setState(() => _busy = true);
    try {
      await ref.read(soumProvider).notifications.updateChannel(
            widget.channel.code,
            isEnabled: enabled,
          );
      ref.invalidate(channelsProvider);
    } on ApiException catch (error) {
      if (mounted) showApiError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _link() async {
    final soum = ref.read(soumProvider);
    setState(() => _busy = true);

    try {
      if (widget.channel.isLinked) {
        await soum.notifications.unlinkTelegram();
        ref.invalidate(channelsProvider);
        return;
      }

      final link = await soum.notifications.linkTelegram();

      if (!mounted) return;
      final strings = SoumStrings.of(context);

      // الرمز لمرّة واحدة ويموت بعد عشر دقائق. لا يُخزَّن ولا يُعاد
      // استعماله: من يلتقط الرابط قبل صاحبه يربط حسابه بإشعارات غيره.
      final opened = await launchUrl(
        Uri.parse(link.deepLink),
        mode: LaunchMode.externalApplication,
      );

      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(
          content: Text(
            opened ? strings.channelTelegramOpening : link.deepLink,
          ),
        ));
    } on ApiException catch (error) {
      if (!mounted) return;
      // 503 هنا ليست عطلًا: المشغّل لم يفعّل تليغرام على الخادم.
      // نُعيد قراءة القنوات فيختفي الخيار من تلقائه.
      if (error.statusCode == 503) {
        ref.invalidate(channelsProvider);
        return;
      }
      showApiError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}

/// صندوق الإشعارات الوارد.
///
/// §10.2: «الإشعار ليس بديلًا عن WebSocket». هذه شاشةُ قراءةٍ لا مصدرُ
/// حالة: لا شيء هنا يغيّر مرحلة رحلة.
class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final inbox = ref.watch(_inboxProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(strings.notificationsTitle),
        actions: [
          IconButton(
            icon: const Icon(Icons.tune_rounded),
            tooltip: strings.channelsTitle,
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const ChannelsScreen()),
            ),
          ),
        ],
      ),
      body: inbox.when(
        loading: () =>
            const Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
        error: (_, _) => Center(child: Text(strings.errorGeneric)),
        data: (rows) => rows.isEmpty
            ? Center(
                child: Text(
                  strings.notificationsEmpty,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              )
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: rows.length,
                separatorBuilder: (_, _) => const Divider(height: 18),
                itemBuilder: (context, index) {
                  final row = rows[index];
                  return ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(readString(row, 'title')),
                    subtitle: Text(readString(row, 'body')),
                  );
                },
              ),
      ),
    );
  }
}

final _inboxProvider = FutureProvider.autoDispose<List<Json>>(
  (ref) => ref.read(soumProvider).notifications.inbox(),
);
