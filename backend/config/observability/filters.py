"""
فلتر يحقن معرّف الحادثة في كل سطر سجلّ.

فلتر لا Formatter مخصّص: الفلتر يُضاف إلى LogRecord نفسه، فيصير الحقل
متاحًا لأي منسّق — النصّي والـJSON معًا — بلا تكرار.

وقيمة "-" حين لا يوجد معرّف مقصودة: سطر بلا معرّف (مهمّة دورية مثلًا)
يجب أن يبقى مقروءًا بالعرض نفسه لا أن يزيح الأعمدة.
"""
import json
import logging

from config.observability.context import get_actor, get_request_id


class RequestContextFilter(logging.Filter):

    def filter(self, record):
        record.request_id = get_request_id() or "-"
        record.actor = get_actor() or "-"
        return True


class JSONFormatter(logging.Formatter):
    """
    منسّق JSON للملفّات — لأن السجلّ الذي يُقرأ بالعين اليوم يُقرأ بأداة
    غدًا، وإعادة تحليل نصّ حرّ لاحقًا أصعب من كتابته منظَّمًا من البداية.

    بلا اعتمادية خارجية: json من المكتبة القياسية يكفي.
    """
    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "actor": getattr(record, "actor", "-"),
            "message": record.getMessage(),
        }

        # الحقول الإضافية التي يمرّرها الكود عبر extra={...}
        for key in ("event", "ride_id", "trip_id", "driver_id", "status_code",
                    "duration_ms", "path", "method", "error_code"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)
