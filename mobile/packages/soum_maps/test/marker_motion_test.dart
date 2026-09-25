import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';

void main() {
  const jableh = GeoPoint(35.3608, 35.9236);
  // ~111 م شمالًا.
  const north = GeoPoint(35.3618, 35.9236);
  const glide = Duration(milliseconds: 2600);

  test('bearing: north is 0, east is 90', () {
    expect(bearingDegrees(jableh, north), closeTo(0, 0.5));
    expect(
      bearingDegrees(jableh, const GeoPoint(35.3608, 35.9250)),
      closeTo(90, 0.5),
    );
  });

  test('shortest turn crosses north instead of spinning around', () {
    expect(lerpAngle(350, 10, 0.5), closeTo(0, 0.001));
  });

  test('glides from old to new position, arriving at the end', () {
    final motion = MarkerMotion(jableh);
    motion.retarget(north, Duration.zero, duration: glide);

    final middle = motion.positionAt(const Duration(milliseconds: 1300));
    expect(middle.lat, greaterThan(jableh.lat));
    expect(middle.lat, lessThan(north.lat));
    expect(motion.positionAt(glide), north);
    expect(motion.isMoving(glide), isFalse);
  });

  test('a new fix mid-glide starts from where the car is, not back', () {
    final motion = MarkerMotion(jableh);
    motion.retarget(north, Duration.zero, duration: glide);
    const at = Duration(milliseconds: 1300);
    final here = motion.positionAt(at);

    motion.retarget(const GeoPoint(35.3628, 35.9236), at, duration: glide);
    expect(motion.positionAt(at), here);
  });

  test('a long jump teleports instead of sliding across the city', () {
    final motion = MarkerMotion(jableh);
    const latakia = GeoPoint(35.5236, 35.7917);
    motion.retarget(latakia, Duration.zero, duration: glide);
    expect(motion.positionAt(Duration.zero), latakia);
  });

  test('GPS jitter does not turn a parked car', () {
    final motion = MarkerMotion(jableh, heading: 90);
    motion.retarget(
      const GeoPoint(35.36081, 35.9236),
      Duration.zero,
      duration: glide,
    );
    expect(motion.headingAt(glide), closeTo(90, 0.001));
  });

  test('car turns toward its direction of travel', () {
    final motion = MarkerMotion(jableh, heading: 90);
    motion.retarget(north, Duration.zero, duration: glide);
    expect(motion.headingAt(glide), closeTo(0, 0.5));
  });
}
