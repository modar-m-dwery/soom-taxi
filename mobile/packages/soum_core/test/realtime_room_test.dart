// T1.6 — «اختبار يقطع المقبس ويثبت تنفيذ الخطوات الثلاث بالترتيب مرّة
// واحدة لا أكثر».
//
// الخطوة الثالثة — نداء `/me/active-ride/` — هي التي تحتاج حراسة: مقبسٌ
// يتقطّع كلّ ثانيتين على شبكة رديئة يُنتج عشرين نداءً في دقيقة لنقطة
// تقرأ طلبًا ورحلةً ودفعة. لذلك تُطلق الإشارة بعد **نجاح** الاتصال لا
// عند كلّ محاولة.

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:stream_channel/stream_channel.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// مقبس مزيّف يُفتح ويُغلق بأمرنا.
class FakeSocket extends StreamChannelMixin<dynamic>
    implements WebSocketChannel {
  FakeSocket(this.uri, {this.failHandshake = false});

  final Uri uri;
  final bool failHandshake;

  final _incoming = StreamController<dynamic>();
  final sent = <String>[];
  bool closed = false;

  @override
  Future<void> get ready =>
      failHandshake ? Future<void>.error(StateError('رُفضت المصافحة')) : Future.value();

  @override
  Stream<dynamic> get stream => _incoming.stream;

  @override
  WebSocketSink get sink => _FakeSink(this);

  /// إطار من الخادم إلى العميل.
  void emit(Map<String, dynamic> frame) => _incoming.add(jsonEncode(frame));

  /// قطعٌ من طرف الخادم — لا إغلاق نظيف من العميل.
  Future<void> drop() async {
    closed = true;
    await _incoming.close();
  }

  @override
  int? get closeCode => closed ? 1006 : null;

  @override
  String? get closeReason => null;

  @override
  String? get protocol => null;
}

class _FakeSink implements WebSocketSink {
  _FakeSink(this._socket);
  final FakeSocket _socket;

  @override
  void add(dynamic data) => _socket.sent.add('$data');

  @override
  Future<void> close([int? closeCode, String? closeReason]) async {
    if (!_socket.closed) {
      _socket.closed = true;
      await _socket._incoming.close();
    }
  }

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future<void> addStream(Stream<dynamic> stream) async {}

  @override
  Future<void> get done => Future.value();
}

void main() {
  test('المفتاح يُمرَّر في مسار الاستعلام', () {
    final room = RealtimeRoom(
      baseWsUrl: 'ws://127.0.0.1:8000',
      path: '/ws/rides/2702/',
      token: 'abc123',
      channelFactory: FakeSocket.new,
    );

    expect(room.uri.toString(), 'ws://127.0.0.1:8000/ws/rides/2702/?token=abc123');
  });

  test('https ← wss في اشتقاق جذر المقابس', () {
    final room = RealtimeRoom(
      baseWsUrl: 'wss://api.soum.sy',
      path: '/ws/driver/1/',
      token: 't',
      channelFactory: FakeSocket.new,
    );
    expect(room.uri.scheme, 'wss');
  });

  test('الأحداث تصل ومعها حكم الحارس', () async {
    late FakeSocket socket;
    final room = RealtimeRoom(
      baseWsUrl: 'ws://test',
      path: '/ws/rides/2/',
      token: 't',
      channelFactory: (uri) => socket = FakeSocket(uri),
    );

    final received = <GuardedEvent>[];
    room.events.listen(received.add);

    await room.connect();
    expect(room.isConnected, isTrue);

    socket.emit({'event_type': 'connection.established', 'group': 'ride_2'});
    socket.emit({
      'event_type': 'ride.snapshot',
      'entity_type': 'ride',
      'entity_id': 2,
      'version': 0,
      'payload': {'ride': <String, dynamic>{}, 'offers': <dynamic>[]},
    });
    socket.emit({
      'event_type': 'offer.created',
      'payload': {
        'entity_type': 'ride',
        'entity_id': 2,
        'version': 1,
        'data': {'id': 5},
      },
    });

    await Future<void>.delayed(const Duration(milliseconds: 60));

    expect(received, hasLength(3));
    expect(received[1].event.isSnapshot, isTrue);
    expect(received[2].verdict, VersionVerdict.accept);
    expect(received.any((e) => e.isStale), isFalse);

    await room.close();
  });

  test('الفجوة تُعلَّم فيُطلب اللحاق بآخر نسخة معروفة', () async {
    late FakeSocket socket;
    final room = RealtimeRoom(
      baseWsUrl: 'ws://test',
      path: '/ws/rides/2/',
      token: 't',
      channelFactory: (uri) => socket = FakeSocket(uri),
    );

    final received = <GuardedEvent>[];
    room.events.listen(received.add);

    await room.connect();

    for (final version in [1, 4]) {
      socket.emit({
        'event_type': 'offer.created',
        'payload': {
          'entity_type': 'ride',
          'entity_id': 2,
          'version': version,
          'data': <String, dynamic>{},
        },
      });
    }

    await Future<void>.delayed(const Duration(milliseconds: 60));

    expect(received.last.needsResync, isTrue);

    room.requestResync('ride', 2);
    final request = jsonDecode(socket.sent.last) as Map<String, dynamic>;
    expect(request['type'], 'resync');
    expect(request['since_version'], 4);

    await room.close();
  });

  test('انقطاع واحد ← إشارة استئناف واحدة، بعد النجاح لا عند المحاولة',
      () async {
    final sockets = <FakeSocket>[];
    final room = RealtimeRoom(
      baseWsUrl: 'ws://test',
      path: '/ws/rides/2/',
      token: 't',
      channelFactory: (uri) {
        final socket = FakeSocket(uri);
        sockets.add(socket);
        return socket;
      },
    );

    var resumeCalls = 0;
    room.onReconnected = () => resumeCalls++;

    final states = <RoomState>[];
    room.states.listen(states.add);

    await room.connect();
    expect(resumeCalls, 0, reason: 'الاتصال الأوّل ليس استئنافًا');

    await sockets.first.drop();
    await Future<void>.delayed(const Duration(milliseconds: 900));

    expect(sockets.length, greaterThanOrEqualTo(2), reason: 'أعاد الاتصال');
    expect(resumeCalls, 1, reason: 'مرّة واحدة لا أكثر');
    expect(states, contains(RoomState.reconnecting));
    expect(room.isConnected, isTrue);

    await room.close();
  });

  test('الإغلاق بأمر المستخدم لا يُعيد الاتصال', () async {
    final sockets = <FakeSocket>[];
    final room = RealtimeRoom(
      baseWsUrl: 'ws://test',
      path: '/ws/rides/2/',
      token: 't',
      channelFactory: (uri) {
        final socket = FakeSocket(uri);
        sockets.add(socket);
        return socket;
      },
    );

    await room.connect();
    await room.close();
    await Future<void>.delayed(const Duration(milliseconds: 900));

    expect(sockets, hasLength(1));
    expect(room.state, RoomState.closed);
  });

  test('فشل المصافحة يُعامَل كانقطاع لا كعطل نهائيّ', () async {
    var attempts = 0;
    final room = RealtimeRoom(
      baseWsUrl: 'ws://test',
      path: '/ws/rides/2/',
      token: 't',
      channelFactory: (uri) {
        attempts++;
        return FakeSocket(uri, failHandshake: attempts < 3);
      },
    );

    await room.connect();
    // التراجع الأسّي: 500ms ثمّ 1000ms — فالمحاولة الثالثة عند 1500ms.
    await Future<void>.delayed(const Duration(milliseconds: 2000));

    expect(attempts, greaterThanOrEqualTo(3));
    expect(room.isConnected, isTrue);

    await room.close();
  });

  test('إطار تالف لا يُسقط الغرفة', () async {
    late FakeSocket socket;
    final room = RealtimeRoom(
      baseWsUrl: 'ws://test',
      path: '/ws/rides/2/',
      token: 't',
      channelFactory: (uri) => socket = FakeSocket(uri),
    );

    final received = <GuardedEvent>[];
    room.events.listen(received.add);

    await room.connect();
    socket.sink.add(null);
    (socket as dynamic)._incoming.add('}{ليس JSON');
    socket.emit({'event_type': 'pong'});
    socket.emit({'event_type': 'driver.arrived', 'payload': <String, dynamic>{}});

    await Future<void>.delayed(const Duration(milliseconds: 60));

    expect(room.isConnected, isTrue);
    expect(received, hasLength(1), reason: 'pong يُبتلع، والتالف يُهمَل');
    expect(received.single.event.type, 'driver.arrived');

    await room.close();
  });
}
