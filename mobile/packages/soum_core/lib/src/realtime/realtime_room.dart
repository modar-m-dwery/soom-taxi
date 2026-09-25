/// غرفة بثّ واحدة — اتصال، إعادة اتصال، وحارس ترتيب.
///
/// قاعدة إعادة الاتصال، §7.3 حرفيًّا:
///
/// > عند عودة المقبس بعد انقطاع: أعد الاشتراك، ثمّ ارسم من اللقطة، ثمّ نادِ
/// > `/me/active-ride/` مرّة واحدة. سجلّ الأحداث في الخادم يحتفظ بآخر خمسين
/// > حدثًا لكلّ كيان لمدّة ساعة، لكنّ اللحاق منه ليس مضمونًا في الفجوات
/// > الطويلة — واللقطة مضمونة دائمًا.
///
/// الخطوتان الأوليان تحدثان هنا: الاتصال يُعاد، والخادم يرسل اللقطة من
/// تلقائه عند القبول. الثالثة مسؤولية المستدعي، ولذلك يخرج `onReconnected`
/// كإشارة صريحة — لا كأثر جانبيّ يُستنتج من تدفّق الأحداث.
///
/// **مرّة واحدة** في الجملة مهمّة: مقبس يتقطّع كلّ ثانيتين على شبكة رديئة
/// يُنتج عشرين نداءً لـ`/me/active-ride/` في دقيقة، وهي نقطة تقرأ رحلةً
/// ورحلةً وطلبًا ودفعة. لذلك الإشارة تُطلق بعد **نجاح** الاتصال لا عند
/// كلّ محاولة، والتراجع الأسّي يباعد المحاولات.
library;

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/json.dart';
import 'realtime_event.dart';
import 'version_guard.dart';

enum RoomState { idle, connecting, connected, reconnecting, closed }

/// حدث مرّ بحارس الترتيب ومعه حكمه.
class GuardedEvent {
  const GuardedEvent(this.event, this.verdict);

  final RealtimeEvent event;
  final VersionVerdict verdict;

  /// فجوة: طبّق الحدث **وأعد** نداء GET المقابل. لا تخمّن ما فات.
  bool get needsResync => verdict == VersionVerdict.gap;

  /// متأخّر — لا تطبّقه.
  bool get isStale => verdict == VersionVerdict.stale;
}

typedef ChannelFactory = WebSocketChannel Function(Uri uri);

class RealtimeRoom {
  RealtimeRoom({
    required this.baseWsUrl,
    required this.path,
    required this.token,
    VersionGuard? guard,
    ChannelFactory? channelFactory,
    this.pingInterval = const Duration(seconds: 25),
    this.maxBackoff = const Duration(seconds: 30),
  })  : guard = guard ?? VersionGuard(),
        _channelFactory = channelFactory ?? WebSocketChannel.connect;

  /// مثل `ws://host:8000` أو `wss://host`.
  final String baseWsUrl;

  /// مثل `/ws/rides/2702/` — كما يعطيه `/me/active-ride/` في `realtime`.
  final String path;

  final String token;
  final VersionGuard guard;
  final Duration pingInterval;
  final Duration maxBackoff;

  final ChannelFactory _channelFactory;

  final _events = StreamController<GuardedEvent>.broadcast();
  final _states = StreamController<RoomState>.broadcast();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _pingTimer;
  Timer? _retryTimer;

  int _attempt = 0;
  bool _closedByUser = false;
  RoomState _state = RoomState.idle;

  /// تُنادى بعد نجاح **إعادة** اتصال — لا بعد الاتصال الأوّل.
  /// هنا موضع النداء الواحد لـ`/me/active-ride/`.
  void Function()? onReconnected;

  Stream<GuardedEvent> get events => _events.stream;
  Stream<RoomState> get states => _states.stream;
  RoomState get state => _state;
  bool get isConnected => _state == RoomState.connected;

  /// §7 في الدليل: «المفتاح يُمرَّر في مسار الاستعلام».
  Uri get uri => Uri.parse('$baseWsUrl$path').replace(
        queryParameters: {'token': token},
      );

  // ---------------------------------------------------------------

  Future<void> connect() async {
    if (_closedByUser) return;
    if (_state == RoomState.connecting || _state == RoomState.connected) return;

    _setState(_attempt == 0 ? RoomState.connecting : RoomState.reconnecting);

    try {
      final channel = _channelFactory(uri);
      _channel = channel;

      await channel.ready;

      final wasRetry = _attempt > 0;
      _attempt = 0;
      _setState(RoomState.connected);
      _startPing();

      _subscription = channel.stream.listen(
        _onFrame,
        onDone: _onDone,
        onError: (Object _) => _onDone(),
        cancelOnError: false,
      );

      if (wasRetry) onReconnected?.call();
    } on Object {
      // فشل المصافحة نفسه. يُعامَل كانقطاع: نفس التراجع، نفس المسار.
      _onDone();
    }
  }

  void _onFrame(dynamic raw) {
    if (raw is! String) return;

    Json frame;
    try {
      frame = asJson(jsonDecode(raw));
    } on FormatException {
      return;
    }
    if (frame.isEmpty) return;

    for (final event in RealtimeEvent.parse(frame)) {
      if (event.isPong) continue;
      _events.add(GuardedEvent(event, guard.inspect(event)));
    }
  }

  void _onDone() {
    _teardownSocket();
    if (_closedByUser) return;

    _setState(RoomState.reconnecting);
    _scheduleRetry();
  }

  /// تراجع أسّي مع سقف.
  ///
  /// بلا سقف تصير المحاولة العاشرة بعد سبعة عشر دقيقة، فيبقى المستخدم بلا
  /// تحديث بعد عودة الشبكة. وبلا تراجع أصلًا يُغرق التطبيقُ خادمًا متعثّرًا
  /// بمحاولة كلّ ملّي ثانية — وهو ما يمنعه من التعافي.
  void _scheduleRetry() {
    _retryTimer?.cancel();

    final backoffMs = (500 * (1 << _attempt.clamp(0, 6)))
        .clamp(500, maxBackoff.inMilliseconds);
    _attempt++;

    _retryTimer = Timer(Duration(milliseconds: backoffMs), connect);
  }

  void _startPing() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(pingInterval, (_) {
      // النبضة تكشف اتصالًا ميتًا لا يُبلِّغ عن نفسه — وهو ما يحدث خلف
      // بوّابات NAT التي تُسقط الجلسات الصامتة بلا إشعار.
      send({'type': 'ping'});
    });
  }

  /// إرسال إلى الخادم — نبض الموقع في غرفة السائق، وطلب اللحاق.
  void send(Json message) {
    final channel = _channel;
    if (channel == null || _state != RoomState.connected) return;
    try {
      channel.sink.add(jsonEncode(message));
    } on Object {
      _onDone();
    }
  }

  /// طلب اللحاق بما فات. يُنادى عند حكم `gap` في غرفة الرحلة.
  ///
  /// الخادم يردّ بأحداث السجلّ إن كانت كافية، وإلّا بلقطة كاملة — وهو
  /// السلوك الصحيح: اللحاق أرخص، واللقطة مضمونة.
  void requestResync(String entityType, int entityId) {
    send({
      'type': 'resync',
      'since_version': guard.versionOf(entityType, entityId),
    });
  }

  void _teardownSocket() {
    _pingTimer?.cancel();
    _pingTimer = null;
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
  }

  void _setState(RoomState next) {
    if (_state == next) return;
    _state = next;
    if (!_states.isClosed) _states.add(next);
  }

  Future<void> close() async {
    _closedByUser = true;
    _retryTimer?.cancel();
    _teardownSocket();
    _setState(RoomState.closed);
    await _events.close();
    await _states.close();
  }
}
