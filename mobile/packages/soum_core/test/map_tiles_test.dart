// مزوّد البلاطات من الخادم، ورابطٌ معطوب لا يترك الخريطة فارغة.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  test('يقرأ المزوّد من الإعداد', () {
    final tiles = MapTileSource.fromJson(const {
      'url_template': 'https://tiles.example/{z}/{x}/{y}.png?key=k',
      'dark_url_template': 'https://tiles.example/dark/{z}/{x}/{y}.png?key=k',
      'attribution': '© Example © OpenStreetMap contributors',
      'max_zoom': 20,
    });
    expect(tiles.urlTemplate, contains('tiles.example'));
    expect(tiles.darkUrlTemplate, contains('/dark/'));
    expect(tiles.maxZoom, 20);
  });

  test('رابط بلا {z}/{x}/{y} يعود إلى OSM بدل خريطةٍ فارغة', () {
    final tiles = MapTileSource.fromJson(const {'url_template': 'https://broken'});
    expect(tiles, MapTileSource.openStreetMap);
  });

  test('خادمٌ أقدم بلا map_tiles: OSM', () {
    final config = AppConfig.fromJson({
      'ride_modes': <String>[],
      'timings': <String, dynamic>{},
      'geometry': <String, dynamic>{},
      'pricing': <String, dynamic>{},
      'server_time': '2026-09-25T20:00:00Z',
    });
    expect(config.mapTiles, MapTileSource.openStreetMap);
  });
}
