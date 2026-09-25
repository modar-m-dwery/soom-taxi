"""
حمل معرّف الحادثة إلى مهامّ Celery، وسجّل ما يفشل منها.

بلا هذا، تنقطع السلسلة عند أول .delay(): الطلب الذي أنشأ الدعوة له
معرّف، والمهمّة التي أنهت صلاحيتها بعد عشرين ثانية لها سطور بلا أب.

الاستدعاء من config/celery.py بعد إنشاء app:

    from config.observability.celery_hooks import install
    install()
"""
import logging

from celery.signals import (
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
)

from config.observability.context import bind, get_request_id

logger = logging.getLogger("celery")

HEADER = "x_request_id"

_tokens = {}


def install():
    before_task_publish.connect(_publish, weak=False)
    task_prerun.connect(_prerun, weak=False)
    task_postrun.connect(_postrun, weak=False)
    task_failure.connect(_failure, weak=False)


# ---------------------------------------------------------------------


def _publish(headers=None, **kwargs):
    """يُنفَّذ في العملية التي تُرسل المهمّة — هنا يوجد المعرّف."""
    if headers is None:
        return

    request_id = get_request_id()

    if request_id:
        headers[HEADER] = request_id


def _prerun(task_id=None, task=None, **kwargs):
    """يُنفَّذ في العامل — هنا نستعيده."""
    request_id = ""

    try:
        request = getattr(task, "request", None)
        request_id = getattr(request, HEADER, "") or ""
    except Exception:
        pass

    name = getattr(task, "name", "?")
    _tokens[task_id] = bind(request_id=request_id or None, actor=f"task:{name}")


def _postrun(task_id=None, **kwargs):
    unbind = _tokens.pop(task_id, None)

    if unbind:
        unbind()


def _failure(task_id=None, exception=None, sender=None, **kwargs):
    """
    مهمّة تسقط اليوم تكتب traceback في سجلّ Celery وحده، بتنسيق مختلف
    وبلا معرّف. فيصير عطل يظهر أثره في القاعدة بلا أن يُربط بسببه.
    """
    logger.exception(
        "task failed: %s", getattr(sender, "name", "?"),
        exc_info=exception,
        extra={"event": "celery.failure", "error_code": "task_failed"},
    )
