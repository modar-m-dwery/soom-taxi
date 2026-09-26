/// التقييم بمنزلةٍ عشريّة واحدة — مقتطَعًا لا مقرَّبًا.
///
/// ‏`toStringAsFixed(1)` يعرض 4.95 «5.0»: خمس نجوم كاملة لسائقٍ لم يبلغها،
/// وتقييمٌ متضخّم يُفقد التقييمات معناها. الاقتطاع بعد تقريب المئات يتفادى
/// أخطاء الفاصلة العائمة (4.3 × 10 = 42.999…).
String formatRating(num rating) {
  final tenths = (rating * 100).round() ~/ 10;
  return (tenths / 10).toStringAsFixed(1);
}

/// عدّادٌ بالدقائق والثواني: «9:58» لا «598 ثانية» — مهلة البحث عشر دقائق.
String formatClock(int seconds) {
  final s = seconds < 0 ? 0 : seconds;
  final hours = s ~/ 3600;
  final minutes = (s % 3600) ~/ 60;
  final rest = (s % 60).toString().padLeft(2, '0');
  if (hours > 0) return '$hours:${minutes.toString().padLeft(2, '0')}:$rest';
  return '$minutes:$rest';
}
