"""
مزوّد التطوير: يطبع الإشعار بدل إرساله.

ليس دميةً فارغة - هو ما يجعل كل ما فوقه (الصندوق، الانقضاء، منع التكرار،
إبطال الرموز) قابلًا للاختبار قبل أن تصل مفاتيح FCM. وحين تصل، لا يتغيّر
شيء فوقه.
"""
import logging

from notifications.backends.base import BaseBackend, SendResult

logger = logging.getLogger("notifications")


class ConsoleBackend(BaseBackend):

    name = "console"

    def send(self, token, notification):
        logger.info(
            "[PUSH:%s] -> %s | %s | %s | data=%s",
            notification.priority,
            token.token[:16] + "…",
            notification.title,
            notification.body,
            notification.data,
        )
        return SendResult.success()


class NullBackend(BaseBackend):
    """لا يرسل ولا يطبع. لاختبارات الحمل وبيئات لا نريد فيها أي ضجيج."""

    name = "null"

    def send(self, token, notification):
        return SendResult.success()
