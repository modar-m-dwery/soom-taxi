"""
البوابة النقدية — الوحيدة العاملة اليوم، والأهمّ في السوق السوري.

النقد ليس "غياب بوابة". هو بوابة كاملة بقواعد خاصة:

  * لا مزوّد خارجي، فلا شبكة ولا فشل عابر ولا مهلة.
  * المال يصل السائق مباشرة لا المنصّة → `settles_to_platform = False`.
  * ولذلك تنقلب إشارة العمولة: المنصّة لا تدين للسائق، بل السائق يدين
    للمنصّة بعمولتها. هذا ما يحوّل الدفتر إلى أداة تسوية حقيقية بدل
    كونه زينة محاسبية.
  * الإعادة لا تُنفَّذ برمجيًا — لا أحد يستطيع سحب نقد من جيب سائق.
    تُدار كتسوية على الرصيد، ولذلك `supports_refund = False`.

نقطة الحسم: التحصيل هنا ليس نداءً بل **تأكيدًا** بأن السائق قبض. ولذلك
`charge` تنجح فورًا، والقيد المحاسبي هو كلّ ما يحدث فعلًا.
"""
from payments.gateways.base import GatewayResult, PaymentGateway


class CashGateway(PaymentGateway):

    code = "cash"
    display_name = "نقدًا للسائق"

    is_online = False
    settles_to_platform = False
    supports_authorize_capture = False
    supports_refund = False
    supports_webhook = False

    # فارغة عمدًا: النقد يعمل بأي عملة.
    supported_currencies = ()

    # النقد يؤكّده إنسان لا مزوّد. هذه الراية هي ما يجعل
    # `PaymentService._authorize_charge` يشترط أن يكون المؤكِّد سائق
    # الرحلة نفسه أو مشغّلًا — لا الزبون.
    requires_manual_confirmation = True

    def check_ready(self):
        # لا شيء يمكن أن يكون ناقصًا. النقد جاهز دائمًا، وهذا سبب وجيه
        # لجعله الافتراضي.
        return True

    def charge(self, payment, context=None):
        """
        لا نداء خارجي. النجاح فوري ونهائي.

        السائق هو من يؤكّد القبض عبر الواجهة، و`PaymentService` هو من
        يفرض أن المؤكِّد هو سائق الرحلة نفسه — لا هذه البوابة. البوابة
        لا تعرف شيئًا عن الصلاحيات، وهذا مقصود.
        """
        return GatewayResult.success(
            reference="",
            payload={
                "method": "cash",
                "collected_by": "driver",
                "trip_id": payment.trip_id,
            },
        )

    def refund(self, payment, amount, reason="", context=None):
        return GatewayResult.permanent(
            "الدفع النقدي لا يُعاد برمجيًا. "
            "استخدم تسوية يدوية على رصيد السائق."
        )
