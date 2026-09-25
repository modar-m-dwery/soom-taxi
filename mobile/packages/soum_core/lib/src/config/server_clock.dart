/// ساعة الخادم — وتصحيح انحراف ساعة الجهاز.
///
/// §0.1 في دليل التكامل يضع `server_time` في ردّ الإعداد ويقول: «قارِنه
/// بساعة الجهاز». والسبب عمليّ لا شكليّ.
///
/// كلّ عدّاد في هذا التطبيق مبنيّ على طابع زمنيّ من الخادم: `expires_at`
/// للطلب، و`expires_at` لبطاقة العرض، و`expires_at` للدعوة — وهذه الأخيرة
/// مهلتها **عشرون ثانية**. جهازٌ ساعتُه متقدّمة نصف دقيقة — وهو شائع على
/// أجهزة رخيصة بلا مزامنة زمنية — يحسب كلّ دعوة منتهيةً قبل أن تُرسم،
/// فيرى السائق «انقضت المهلة» على دعوة وصلته للتوّ.
///
/// والانحراف في الاتجاه الآخر أسوأ: عدّادٌ يقول «باقٍ ١٥ ثانية» بينما
/// الخادم ألغى الدعوة فعلًا، فيضغط السائق «اقبل» ويقرأ خطأً لا ذنب له فيه.
///
/// ومصدر الزمن قابل للحقن. السبب اختباريّ محض وضروريّ: في اختبار ودجت
/// يقدّم `tester.pump` مؤقّتاتِ Flutter بينما ساعة النظام لا تتحرّك، فعدّادٌ
/// يقرأ `DateTime.now()` يُطلِق نبضته ولا يتغيّر رقمه — ويمرّ اختبارٌ لم
/// يقِس شيئًا. الحقن يجعل العدّاد مقيسًا فعلًا.
// ignore_for_file: prefer_initializing_formals
// السبب: Dart يمنع معاملًا مسمّى يبدأ بشرطة سفلية.
class ServerClock {
  const ServerClock(this.skew, {DateTime Function()? source})
      : _source = source;

  /// فارق ساعة الخادم عن ساعة الجهاز وقت قراءة الإعداد.
  final Duration skew;

  final DateTime Function()? _source;

  static const ServerClock synced = ServerClock(Duration.zero);

  /// ساعة ثابتة للاختبارات.
  factory ServerClock.fixed(DateTime Function() source) =>
      ServerClock(Duration.zero, source: source);

  /// الآن بساعة الخادم.
  DateTime now() => (_source ?? DateTime.now)().add(skew);

  /// الثواني المتبقّية حتّى لحظة من الخادم — بصفر أدنى، ومقرَّبة لأعلى.
  ///
  /// التقريب لأعلى لا بالبتر: مهلةٌ باقٍ منها 1.9 ثانية تُعرض «2» لا «1».
  /// البتر يجعل العدّاد يبدأ من رقم أقلّ ممّا أعطاه الخادم — فيبدو أنّ
  /// ثانيةً ضاعت قبل أن يُرسَم العدّاد.
  int secondsUntil(DateTime? deadline) {
    if (deadline == null) return 0;
    final millis = deadline.difference(now()).inMilliseconds;
    if (millis <= 0) return 0;
    return (millis / 1000).ceil();
  }

  Duration remaining(DateTime? deadline) =>
      Duration(seconds: secondsUntil(deadline));

  bool hasPassed(DateTime? deadline) =>
      deadline != null && secondsUntil(deadline) == 0;

  /// انحرافٌ يتجاوز عشر ثوانٍ يستحقّ تنبيهًا للمستخدم: العدّادات ستبدو
  /// خاطئة له مهما صحّحنا، لأنّ ساعة قفل شاشته تقول غير ذلك.
  bool get isDeviceClockSuspect => skew.abs() > const Duration(seconds: 10);
}
