import '../models/json.dart';
import '../network/api_client.dart';

/// إعلانٌ في مكانٍ من التطبيق — يُعرض فقط حين يفعّل المشغّل ميزة `ads`.
class AdItem {
  const AdItem({
    required this.id,
    required this.title,
    required this.imageUrl,
    this.linkUrl = '',
    this.serviceCode = '',
  });

  final int id;
  final String title;

  /// مطلقٌ جاهز للتحميل — بُني من عنوان الخادم.
  final String imageUrl;
  final String linkUrl;
  final String serviceCode;

  bool get opensLink => linkUrl.startsWith('https://');
}

class AdsApi {
  AdsApi(this._client, this._origin);

  final ApiClient _client;

  /// `http(s)://host:port` — مسار الصورة من الخادم نسبيّ.
  final String _origin;

  Future<List<AdItem>> list(String placement, {String? area}) async {
    final body = await _client.get<dynamic>('/ads/', query: {
      'placement': placement,
      'area': ?area,
    });
    return [
      for (final row in (body as List? ?? const []))
        if (row is Map)
          () {
            final json = row.cast<String, dynamic>();
            return AdItem(
              id: readInt(json, 'id'),
              title: readString(json, 'title'),
              imageUrl: '$_origin${readString(json, 'image_url')}',
              linkUrl: readString(json, 'link_url', fallback: ''),
              serviceCode: readString(json, 'service_code', fallback: ''),
            );
          }(),
    ];
  }

  /// ظهورٌ أو نقرة. الفشل صامت: عدّادٌ لا يُسقط شاشة.
  Future<void> event(int id, String kind) async {
    try {
      await _client.post<dynamic>('/ads/$id/event/', body: {'kind': kind});
    } on Object {
      // لا شيء.
    }
  }
}
