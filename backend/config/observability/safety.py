"""
أدوات صغيرة تحلّ نمطين وجدهما التدقيق في عشرات المواضع.

النمط الأول: `except Exception: pass` — واحد وستون معالجًا، ستّة وخمسون
منها بلا أي تسجيل. كثير منها *مقصود* فعلًا (فشل بثّ حدث لا يجوز أن
يُسقط رحلة اكتملت)، لكن المقصود يُسجَّل، والمبتلَع لا.

النمط الثاني: `transaction.on_commit(_go)` حيث `_go` يفعل ثلاثة أشياء —
ففشل الأول يمنع الثاني والثالث. وهذا ما يترك سائقًا BUSY إلى الأبد بعد
رحلة أُغلقت بنجاح.
"""
import functools
import logging

logger = logging.getLogger("safety")


def swallow(logger_name="safety", event="", reraise=False):
    """
    بديل `except Exception: pass` — يبتلع لكنه يترك أثرًا.

        with swallow("presence", event="engagement.sync"):
            EngagementResolver.sync(driver_id)

    نفس السلوك تمامًا من الخارج، والفرق الوحيد أنك تعرف حين يقع.
    """
    return _Swallow(logger_name, event, reraise)


class _Swallow:

    def __init__(self, logger_name, event, reraise):
        self._logger = logging.getLogger(logger_name)
        self._event = event
        self._reraise = reraise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            return False

        self._logger.exception(
            "swallowed: %s", self._event or "unnamed",
            extra={"event": self._event or "swallowed"},
        )

        return not self._reraise


def run_all(*steps, event=""):
    """
    ينفّذ كل الخطوات ولو سقطت إحداها — للاستعمال داخل on_commit.

        transaction.on_commit(lambda: run_all(
            lambda: EventBus.publish(...),
            lambda: EventBus.publish(...),
            lambda: EngagementResolver.sync(driver_id),
            event="trip.completed",
        ))

    الترتيب محفوظ، وكل خطوة مستقلّة عن فشل ما قبلها. هذا هو الفرق بين
    «تعذّر إعلام الزبون» و«السائق مشغول إلى الأبد».

    يرجّع عدد الخطوات التي فشلت — صفر يعني أن كل شيء تمّ.
    """
    failures = 0

    for index, step in enumerate(steps):
        try:
            step()
        except Exception:
            failures += 1
            logger.exception(
                "on_commit step %s/%s failed: %s",
                index + 1, len(steps), event or "unnamed",
                extra={"event": f"{event or 'on_commit'}.step_failed"},
            )

    return failures


def guarded(event=""):
    """
    مزيّن لمعالجات الـWebSocket.

    اليوم أي استثناء داخل معالج في realtime/consumers.py يُسقط اتصال
    السائق كاملًا (رمز 1011) بلا سطر واحد — والتطبيق يعيد الاتصال فورًا
    فلا يلاحظ أحد أن مئة سائق فقدوا اتصالهم في تلك اللحظة.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except Exception:
                logging.getLogger("realtime").exception(
                    "consumer handler failed: %s", event or func.__name__,
                    extra={"event": f"ws.{event or func.__name__}.failed"},
                )
                try:
                    await self.send_json({
                        "event_type": "error",
                        "detail": "تعذّر تنفيذ العملية. أعد المحاولة.",
                        "code": "ws.handler_failed",
                    })
                except Exception:
                    pass
                return None
        return wrapper
    return decorator
