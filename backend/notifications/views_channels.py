"""
نقاط القنوات: ماذا يملك المستخدم، وكيف يربط تليغرام، وكيف يرتّب تفضيلاته.
"""
import logging

from django.conf import settings
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status
from catalog.permissions import requires_feature, requires_service
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.openapi import ErrorResponse
from config.throttling import TrustedAnonThrottle, WriteThrottle
from notifications.channels.registry import all_channels, get_channel
from notifications.models import UserChannelPreference
from notifications.services.telegram_link import TelegramLinkService


logger = logging.getLogger("notifications")


# =====================================================================
# المخطّطات
# =====================================================================


class ChannelStateSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    configured = serializers.BooleanField(
        help_text="هل اشترك المشغّل بهذه القناة على الخادم أصلًا."
    )
    requires_linking = serializers.BooleanField(
        help_text="هل تحتاج ربطًا من المستخدم (تليغرام مثلًا)."
    )
    linked = serializers.BooleanField(
        help_text="هل ربط هذا المستخدم عنوانه عليها."
    )
    enabled = serializers.BooleanField()
    priority = serializers.IntegerField(
        help_text="الأصغر يُجرَّب أوّلًا."
    )


class ChannelListSerializer(serializers.Serializer):
    channels = ChannelStateSerializer(many=True)


class UpdateChannelSerializer(serializers.Serializer):
    is_enabled = serializers.BooleanField(required=False)
    priority = serializers.IntegerField(
        required=False, min_value=1, max_value=999
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "أرسل is_enabled أو priority على الأقلّ."
            )
        return attrs


class TelegramLinkSerializer(serializers.Serializer):
    code = serializers.CharField()
    deep_link = serializers.CharField(
        help_text="افتح هذا الرابط في تليغرام واضغط «ابدأ»."
    )
    expires_in_seconds = serializers.IntegerField()


# =====================================================================
# النقاط
# =====================================================================


class MyChannelsView(APIView):
    """GET /api/v1/me/notification-channels/"""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        operation_id="my_notification_channels",
        summary="Channels available to me",
        description=(
            "Which delivery channels exist, which the operator has "
            "configured, and which this user has linked and enabled. "
            "`priority` orders the delivery chain — lower is tried first, "
            "and the first channel that delivers stops the chain."
        ),
        responses={200: ChannelListSerializer},
    )
    def get(self, request):
        preferences = {
            row.channel: row
            for row in UserChannelPreference.objects.filter(user=request.user)
        }

        payload = []

        for channel in all_channels():
            preference = preferences.get(channel.code)
            linked = bool(
                (preference.address if preference else "")
                or (
                    channel.resolve_address(request.user)
                    if channel.requires_address
                    else True
                )
            )

            payload.append({
                "code": channel.code,
                "label": channel.label,
                "configured": channel.is_configured(),
                "requires_linking": channel.requires_address,
                "linked": linked,
                "enabled": (
                    preference.is_enabled if preference
                    else channel.default_enabled
                ),
                "priority": preference.priority if preference else 100,
            })

        return Response({"channels": payload}, status=status.HTTP_200_OK)


class UpdateChannelView(APIView):
    """PATCH /api/v1/me/notification-channels/{code}/"""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [WriteThrottle]

    @extend_schema(
        tags=["Notifications"],
        operation_id="update_notification_channel",
        summary="Enable, disable or reorder a channel",
        request=UpdateChannelSerializer,
        responses={200: ChannelStateSerializer, 404: ErrorResponse},
        examples=[
            OpenApiExample(
                "Prefer Telegram over push",
                request_only=True,
                value={"is_enabled": True, "priority": 50},
            ),
        ],
    )
    def patch(self, request, code):
        channel = get_channel(code)

        if channel is None:
            return Response(
                {"detail": "قناة غير معروفة."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = UpdateChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        preference, _ = UserChannelPreference.objects.get_or_create(
            user=request.user,
            channel=code,
            defaults={
                "is_enabled": channel.default_enabled,
                "priority": 100,
            },
        )

        for field, value in serializer.validated_data.items():
            setattr(preference, field, value)

        preference.save()

        return Response(
            {
                "code": channel.code,
                "label": channel.label,
                "configured": channel.is_configured(),
                "requires_linking": channel.requires_address,
                "linked": bool(preference.address) or not channel.requires_address,
                "enabled": preference.is_enabled,
                "priority": preference.priority,
            },
            status=status.HTTP_200_OK,
        )


class TelegramLinkView(APIView):
    """POST /api/v1/notifications/channels/telegram/link/"""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, requires_feature("telegram_channel")]
    throttle_classes = [WriteThrottle]

    @extend_schema(
        tags=["Notifications"],
        operation_id="telegram_link",
        summary="Start linking a Telegram account",
        description=(
            "Returns a one-time deep link. Open it in Telegram and press "
            "Start; the bot cannot message a user who has not done this. "
            "The code is single-use and expires."
        ),
        request=None,
        responses={201: TelegramLinkSerializer, 503: ErrorResponse},
    )
    def post(self, request):
        from notifications.channels.telegram import TelegramChannel

        if not TelegramChannel().is_configured():
            return Response(
                {"detail": "قناة تليغرام غير مفعّلة على الخادم."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        code, deep_link = TelegramLinkService.issue(request.user)

        return Response(
            {
                "code": code,
                "deep_link": deep_link,
                "expires_in_seconds": int(
                    getattr(settings, "TELEGRAM_LINK_TTL_SECONDS", 600)
                ),
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["Notifications"],
        operation_id="telegram_unlink",
        summary="Unlink my Telegram account",
        responses={204: None},
    )
    def delete(self, request):
        TelegramLinkService.unlink(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelegramWebhookView(APIView):
    """
    POST /api/v1/notifications/webhooks/telegram/

    تليغرام ينادي هذه النقطة، لا مستخدم — فلا مصادقة توكن هنا. الحارس هو
    رمز سرّي في المسار نفسه (`setWebhook` بمسار يحمله)، أو ترويسة
    `X-Telegram-Bot-Api-Secret-Token` التي يرسلها تليغرام إن ضُبطت.

    ولماذا نردّ 200 دائمًا: تليغرام يعيد إرسال أيّ تحديث لم يُجَب عليه
    بنجاح، ويُبطئ الطابور كلّه إن تكرّر الفشل. تحديثٌ لا نفهمه يُتجاهَل
    بهدوء ولا يُعاد إلينا إلى الأبد.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [TrustedAnonThrottle]

    @extend_schema(
        tags=["Notifications"],
        operation_id="telegram_webhook",
        summary="Telegram bot webhook",
        description=(
            "Called by Telegram, not by clients. Handles `/start <code>` to "
            "bind a chat to a user. Always answers 200 so Telegram does not "
            "re-queue updates it cannot deliver."
        ),
        request=None,
        responses={200: None},
    )
    def post(self, request):
        secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")

        if secret:
            sent = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not secrets_equal(sent, secret):
                # 403 هنا لا 200: هذا ليس تحديثًا من تليغرام أصلًا.
                return Response(
                    {"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN
                )

        try:
            self._handle(request.data or {})
        except Exception:  # noqa: BLE001
            logger.exception("telegram: انهارت معالجة التحديث")

        return Response({"ok": True}, status=status.HTTP_200_OK)

    # -----------------------------------------------------------------

    @staticmethod
    def _handle(update):
        message = update.get("message") or update.get("edited_message") or {}
        text = (message.get("text") or "").strip()
        chat = message.get("chat") or {}
        chat_id = chat.get("id")

        if not chat_id or not text.startswith("/start"):
            return

        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            _reply(
                chat_id,
                "افتح رابط الربط من التطبيق ليكتمل التفعيل.",
            )
            return

        user = TelegramLinkService.redeem(parts[1].strip(), chat_id)

        if user is None:
            _reply(
                chat_id,
                "رابط الربط غير صالح أو انتهت صلاحيته. اطلب رابطًا جديدًا "
                "من التطبيق.",
            )
            return

        _reply(chat_id, "تمّ الربط. ستصلك إشعارات سووم تكسي هنا.")


def secrets_equal(a, b):
    """مقارنة بزمن ثابت: مقارنة عادية تسرّب طول البادئة الصحيحة."""
    import hmac

    return hmac.compare_digest(str(a or ""), str(b or ""))


def _reply(chat_id, text):
    """
    ردّ تأكيد للمستخدم. فشله لا يُسقط الربط: الربط تمّ في القاعدة، والرسالة
    مجاملة. رفع خطأ هنا كان سيجعل تليغرام يعيد التحديث فيُستهلك رمزٌ مات.
    """
    from notifications.channels.telegram import TelegramChannel

    try:
        TelegramChannel()._send(chat_id, text)
    except Exception:  # noqa: BLE001
        logger.warning("telegram: تعذّر إرسال ردّ التأكيد إلى %s", chat_id)
