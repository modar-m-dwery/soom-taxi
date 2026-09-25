// نبضة الموقع تحمل علامة التزييف — بدونها لا يرى الخادم Fake GPS أبدًا.

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:soum_driver/features/presence/location_fix.dart';
import 'package:soum_driver/features/presence/presence_state.dart';

Position _position({
  double speed = 8.5,
  double heading = 120,
  double accuracy = 6,
  bool mocked = false,
  bool hasHeading = true,
}) =>
    Position(
      latitude: 33.5138,
      longitude: 36.2765,
      timestamp: DateTime(2026, 9, 25, 8),
      accuracy: accuracy,
      altitude: 690,
      altitudeAccuracy: 3,
      heading: heading,
      headingAccuracy: 5,
      speed: speed,
      speedAccuracy: 1,
      isMocked: mocked,
      hasHeading: hasHeading,
    );

void main() {
  test('الإطار يحمل السرعة والاتجاه والدقّة وعلامة التزييف', () {
    final frame = LocationFix.fromPosition(_position()).toFrame();

    expect(frame['type'], 'location.update');
    expect(frame['lat'], 33.5138);
    expect(frame['lng'], 36.2765);
    expect(frame['speed'], 8.5);
    expect(frame['heading'], 120);
    expect(frame['accuracy'], 6);
    expect(frame['mocked'], isFalse,
        reason: 'false صريح لا غياب: الخادم يميّز تطبيقًا يفحص');
  });

  test('موقعٌ من تطبيق تزييف يُعلَن للخادم', () {
    final fix = LocationFix.fromPosition(_position(mocked: true));
    expect(fix.mocked, isTrue);
    expect(fix.toFrame()['mocked'], isTrue);
  });

  test('القيم «غير المعروفة» لا تُرسل أرقامًا مضلّلة', () {
    // iOS يعطي -1 لسرعة واتجاه لا يعرفهما؛ أندرويد يعطي اتجاهًا صفرًا
    // بلا hasHeading حين لم يحسب اتجاهًا.
    final unknown = LocationFix.fromPosition(
      _position(speed: -1, heading: -1, accuracy: 0),
    ).toFrame();
    expect(unknown.containsKey('speed'), isFalse);
    expect(unknown.containsKey('heading'), isFalse);
    expect(unknown.containsKey('accuracy'), isFalse);

    final noBearing = LocationFix.fromPosition(
      _position(heading: 0, hasHeading: false),
    ).toFrame();
    expect(noBearing.containsKey('heading'), isFalse);

    final north = LocationFix.fromPosition(_position(heading: 0)).toFrame();
    expect(north['heading'], 0, reason: 'صفرٌ مع hasHeading يعني شمالًا فعلًا');
  });

  test('الموقع المزيّف مانعٌ مصنَّف تترجمه الواجهة', () {
    const state = PresenceState(
      stage: PresenceStage.onlineNoHeartbeat,
      blocker: PresenceBlocker.mockLocation,
    );
    expect(state.isOnline, isTrue);
    expect(state.isMatchable, isFalse,
        reason: 'موقعٌ مرفوض لا يُحدّث last_location_at');
  });
}
