import '../models/json.dart';
import '../network/api_client.dart';

class RatingTag {
  const RatingTag({
    required this.code,
    required this.label,
    required this.polarity,
  });

  final String code;
  final String label;

  /// `positive` أو `negative` — تُستعمل لفصل الوسوم في الواجهة.
  final String polarity;

  bool get isNegative => polarity == 'negative';

  factory RatingTag.fromJson(Json json) => RatingTag(
        code: readString(json, 'code'),
        label: readString(json, 'label'),
        polarity: readString(json, 'polarity'),
      );
}

class FeedbackApi {
  FeedbackApi(this._client);

  final ApiClient _client;

  Future<List<RatingTag>> tags() async {
    final body = await _client.get<dynamic>('/rating-tags/');
    return readResults(body).map(RatingTag.fromJson).toList(growable: false);
  }

  /// §6.2 في وثيقة المنتج: تحت ثلاث نجوم يصير السبب إلزاميًّا — وسمٌ أو
  /// تعليق. نجمةٌ بلا سبب لا تُصلح شيئًا ولا تدخل في أيّ قرار.
  ///
  /// التحقّق يُفرض في الواجهة قبل الإرسال، لا لأنّ الخادم لا يفرضه، بل
  /// لأنّ رسالة خطأ بعد الإرسال تجربةٌ أسوأ من حقل إلزاميّ واضح.
  Future<Json> rate({
    required int rideId,
    required int rating,
    List<String> tags = const [],
    String? comment,
  }) async {
    assert(rating >= 1 && rating <= 5, 'التقييم من 1 إلى 5');
    assert(
      rating >= 3 || tags.isNotEmpty || (comment?.isNotEmpty ?? false),
      'تقييم دون ثلاث نجوم يحتاج وسمًا أو تعليقًا',
    );

    // الحقل في الخادم `score` لا `rating` — `SubmitRatingRequest` في
    // المخطّط. بالاسم الخطأ كان كلّ تقييم يُردّ بـ400 ولا يُخزَّن شيء.
    return asJson(await _client.post<dynamic>('/trips/$rideId/rate/', body: {
      'score': rating,
      if (tags.isNotEmpty) 'tags': tags,
      if (comment != null && comment.isNotEmpty) 'comment': comment,
    }));
  }

  Future<Json> ratingState(int rideId) async =>
      asJson(await _client.get<dynamic>('/trips/$rideId/rating/'));

  Future<Json> mySummary() async =>
      asJson(await _client.get<dynamic>('/me/rating/'));

  // -----------------------------------------------------------------
  // الشكاوى — نافذة 30 يومًا، أطول من التقييم عمدًا: المشكلة قد تتكشّف
  // متأخّرة (خصم مالي، غرض منسيّ).
  // -----------------------------------------------------------------

  Future<List<Json>> complaints() async =>
      readResults(await _client.get<dynamic>('/complaints/'));

  Future<Json> openComplaint({
    required int rideId,
    required String category,
    required String description,
  }) async =>
      // `ride_id` لا `ride` — كما في `ComplaintCreateRequest`. بالاسم
      // الخطأ كانت كلّ شكوى تُردّ بـ400.
      asJson(await _client.post<dynamic>('/complaints/', body: {
        'ride_id': rideId,
        'category': category,
        'description': description,
      }));

  Future<Json> complaint(int id) async =>
      asJson(await _client.get<dynamic>('/complaints/$id/'));
}
