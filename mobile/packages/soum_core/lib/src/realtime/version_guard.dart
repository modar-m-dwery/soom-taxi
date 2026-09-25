/// حارس الترتيب — §7.3 و§12.2 في دليل التكامل.
///
/// > كلّ حدث يحمل رقمًا متصاعدًا لكلّ كيان. إن وصلك حدث برقم أصغر ممّا عندك
/// > فهو متأخّر — أهمِله. وإن قفز الرقم أكثر من واحد فقد فاتك حدث: أعد نداء
/// > GET المقابل بدل تخمين ما فات. هذا السطران يمنعان أكثر أخطاء التطبيقات
/// > الحيّة شيوعًا.
///
/// لماذا يقع الخطأ أصلًا: البثّ عبر Redis لا يضمن ترتيبًا بين اتصالين، وإعادة
/// الاتصال بعد انقطاع تُدخل أحداثًا وصلت من مسارين. فيصل `offer.expired`
/// قبل `offer.created` للعرض نفسه — فتُزيل الشاشة عرضًا لم تضفه بعد، ثمّ
/// تضيفه فيبقى معلّقًا إلى الأبد.
///
/// النسخة تُحسب لكلّ كيان لا عالميًّا: `events:version:{entity_type}:{id}`
/// عدّاد مستقلّ في Redis لكلّ رحلة.
library;

import 'realtime_event.dart';

enum VersionVerdict {
  /// بالترتيب — طبّقه.
  accept,

  /// أقدم ممّا عندنا — أهمله بصمت.
  stale,

  /// قفزة: فاتنا حدث أو أكثر. طبّقه **و**أعد نداء GET المقابل.
  gap,

  /// بلا نسخة: حدث زائل (`driver.location`) أو رسالة تحكّم.
  /// يمرّ دائمًا — «آخر قيمة تفوز» لا معنى لترتيبها.
  unversioned,
}

class VersionGuard {
  /// "نوع:معرّف" ← آخر نسخة مطبَّقة.
  final Map<String, int> _seen = {};

  /// آخر نسخة معروفة لكيان — تُرسل في `resync` كـ`since_version`.
  int versionOf(String entityType, int entityId) =>
      _seen['$entityType:$entityId'] ?? 0;

  VersionVerdict inspect(RealtimeEvent event) {
    final version = event.version;
    final entityType = event.entityType;
    final entityId = event.entityId;

    if (version == null || entityType == null || entityId == null) {
      return VersionVerdict.unversioned;
    }

    final key = '$entityType:$entityId';
    final last = _seen[key];

    // اللقطة تعيد ضبط العدّاد مهما كانت قيمتها.
    //
    // الحالة التي تفرض ذلك: إعادة اتصال بعد انقطاع طويل. سجلّ الأحداث في
    // الخادم يحتفظ بخمسين حدثًا لساعة، فقد تعود اللقطة بنسخة أعلى بكثير
    // ممّا عندنا — أو أقلّ، إن كان Redis أُفرغ. الاعتماد على اللقطة أسلم
    // في الحالتين: هي مضمونة دائمًا، واللحاق ليس كذلك.
    if (event.isSnapshot) {
      _seen[key] = version;
      return VersionVerdict.accept;
    }

    if (last == null) {
      // أوّل حدث لهذا الكيان. لا نعرف ما سبقه، فلا ندّعي فجوة: الاشتراك
      // يبدأ باللقطة عادةً، وادّعاء فجوة هنا يُطلق نداء GET زائدًا مع كلّ
      // كيان جديد — وهو ما يُغرق الخادم عند فتح قائمة طويلة.
      _seen[key] = version;
      return VersionVerdict.accept;
    }

    if (version <= last) return VersionVerdict.stale;

    _seen[key] = version;

    return version == last + 1 ? VersionVerdict.accept : VersionVerdict.gap;
  }

  /// عند تسجيل الخروج أو تبديل المستخدم.
  void reset() => _seen.clear();

  void forget(String entityType, int entityId) =>
      _seen.remove('$entityType:$entityId');
}
