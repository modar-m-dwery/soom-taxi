"""
Channels لا يفهم DRF TokenAuthentication تلقائيًا. هذا middleware يقرأ
التوكن من (بالأولوية):
    1) query string:  wss://host/ws/driver/5/?token=abc123
    2) header مخصص:   Sec-WebSocket-Protocol أو Authorization (لو العميل
       يدعم إرسال headers، مثل تطبيقات Flutter عبر بعض المكتبات)

ويضع request.user في scope["user"] بنفس طريقة عمل DRF Token، بحيث
الـconsumers تتعامل مع self.scope["user"] تمامًا كـrequest.user.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def get_user_from_token(token_key):
    from rest_framework.authtoken.models import Token

    try:
        token = Token.objects.select_related("user").get(key=token_key)
    except Token.DoesNotExist:
        return AnonymousUser()

    if not token.user.is_active:
        return AnonymousUser()

    from config.security import token_expired

    if token_expired(token):
        return AnonymousUser()

    return token.user


class TokenAuthMiddleware(BaseMiddleware):

    async def __call__(self, scope, receive, send):
        token_key = self._extract_token(scope)

        if token_key:
            scope["user"] = await get_user_from_token(token_key)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)

    @staticmethod
    def _extract_token(scope):
        # 1) query string: ?token=xxx
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)

        if "token" in query_params:
            return query_params["token"][0]

        # 2) headers: Authorization: Token xxx
        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization")

        if auth_header:
            try:
                prefix, token_key = auth_header.decode().split(" ", 1)
                if prefix.lower() == "token":
                    return token_key
            except ValueError:
                return None

        return None


def TokenAuthMiddlewareStack(inner):
    """
    استخدمها بدل AuthMiddlewareStack القياسية (التي تعتمد على session/cookies
    وغير مناسبة لتطبيق موبايل يعتمد على Token).
    """
    return TokenAuthMiddleware(inner)