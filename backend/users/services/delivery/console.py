"""
خلفية الطابعة — للتطوير وحده.

ترفض العمل حين `DEBUG=False` أو `DEPLOYMENT_ENV=production`. الرفض هنا
تكرار مقصود لما يفعله `settings.py` عند الإقلاع: الحارس الأول قد يُلتفّ
عليه بمتغيّر بيئة خاطئ، وهذا الثاني يمنع طباعة رموز دخول حقيقية في
سجلّات خادم إنتاجي.
"""
import logging

from django.conf import settings

from users.services.delivery.base import (
    DeliveryResult,
    NotConfigured,
    OTPDeliveryBackend,
)


logger = logging.getLogger(__name__)


class ConsoleOTPBackend(OTPDeliveryBackend):

    name = "console"

    def check_ready(self):
        deployment = str(
            getattr(settings, "DEPLOYMENT_ENV", "development")
        ).lower()

        if deployment == "production" or not getattr(settings, "DEBUG", False):
            raise NotConfigured(
                "خلفية الطابعة للتطوير فقط. اضبط OTP_DELIVERY_BACKEND "
                "على مزوّد رسائل حقيقي."
            )

        return True

    def send(self, phone, code, context=None):
        self.check_ready()

        # الطباعة الوحيدة للرمز في المشروع كلّه، ومحروسة بحارسين.
        logger.info("OTP[dev] → %s : %s", phone, code)
        print(f"[OTP] {phone} → {code}")

        return DeliveryResult.success(reference="console")
