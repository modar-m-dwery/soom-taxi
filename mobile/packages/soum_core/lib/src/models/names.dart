/// أسماء الأشخاص كما تُعرض قبل الثقة وبعدها.
///
/// ‏`driver_name` يصل كاملًا من الخادم. قبل قبول السائق لا يُعرض كاملًا
/// (قرار الخصوصية في وثيقة المنتج): الاسم الكامل مع نوع السيارة ولونها يكفي
/// لتعقّب السائق خارج العمل.
library;

/// الاسم الأوّل — ما يكفي ليعرف الزبون من سيأتيه.
String firstName(String fullName) {
  final trimmed = fullName.trim();
  if (trimmed.isEmpty) return '';
  return trimmed.split(RegExp(r'\s+')).first;
}

/// «محمد ع.» — الاسم الأوّل وأوّل حرف من الثاني، بلا أداة التعريف.
String shortName(String fullName) {
  final words = fullName.trim().split(RegExp(r'\s+'))
    ..removeWhere((w) => w.isEmpty);
  if (words.isEmpty) return '';
  if (words.length == 1) return words.first;
  // «العلي» ← «ع.» لا «ا.»: أداة التعريف لا تميّز أحدًا.
  var family = words[1];
  if (family.startsWith(_definiteArticle) &&
      family.length > _definiteArticle.length) {
    family = family.substring(_definiteArticle.length);
  }
  // الحرف العربيّ وحدةٌ واحدة في UTF-16، والتشكيل يلحقه لا يسبقه.
  return '${words.first} ${String.fromCharCode(family.runes.first)}.';
}

const _definiteArticle = 'ال';
