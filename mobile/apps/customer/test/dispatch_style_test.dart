import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_customer/features/home/request_sheet.dart';

AppConfig _config(List<String> modes, List<String> invitable) =>
    AppConfig.fromJson({
      'area_code': 'JAB',
      'ride_modes': modes,
      'invitation_allowed_modes': invitable,
      'timings': <String, dynamic>{},
      'geometry': <String, dynamic>{},
    });

void main() {
  test('offers default to standard, never to an invitation-only mode', () {
    final config = _config(['fast', 'express', 'standard', 'saving'], ['fast', 'express']);
    expect(modeForStyle(DispatchStyle.offers, config), 'standard');
    expect(offerModes(config), ['standard', 'saving']);
  });

  test('nearest prefers fast, pick prefers express', () {
    final config = _config(['fast', 'express', 'standard'], ['fast', 'express']);
    expect(modeForStyle(DispatchStyle.nearest, config), 'fast');
    expect(modeForStyle(DispatchStyle.pick, config), 'express');
  });

  test('operator switching off invitations hides nearest and pick', () {
    final config = _config(['fast', 'express', 'standard'], []);
    expect(modeForStyle(DispatchStyle.nearest, config), isNull);
    expect(modeForStyle(DispatchStyle.pick, config), isNull);
    expect(modeForStyle(DispatchStyle.offers, config), 'standard');
  });

  test('chosen class is kept only if the area still offers it', () {
    final config = _config(['standard', 'saving'], []);
    expect(
      modeForStyle(DispatchStyle.offers, config, offersMode: 'saving'),
      'saving',
    );
    expect(
      modeForStyle(DispatchStyle.offers, config, offersMode: 'shared'),
      'standard',
    );
  });

  test('sharing: offers become shared; nearest/pick need shared invitations', () {
    final closed = _config(['fast', 'express', 'standard', 'shared'], ['fast', 'express']);
    expect(modeForStyle(DispatchStyle.offers, closed, shared: true), 'shared');
    expect(modeForStyle(DispatchStyle.nearest, closed, shared: true), isNull);
    expect(offerModes(closed), ['standard']);

    final open = _config(['fast', 'shared'], ['fast', 'shared']);
    expect(modeForStyle(DispatchStyle.pick, open, shared: true), 'shared');
  });

  test('sharing unavailable when the area does not offer it', () {
    final config = _config(['standard'], []);
    expect(modeForStyle(DispatchStyle.offers, config, shared: true), isNull);
  });

  test('radius options are parsed and ignore junk', () {
    final geometry = AreaGeometry.fromJson({
      'search_radius_options_km': [0.5, 1, 'x', -2, 5],
    });
    expect(geometry.searchRadiusOptionsKm, [0.5, 1.0, 5.0]);
  });
}
