"""
إعداد السجلّات — يُستورد من settings.py بسطر واحد.

الوضع قبل هذا الملف: ثلاثة مُسجِّلات مُعدّة (`django`, `config`, `health`)
وبلا مُسجِّل `root`. أي أن كل `logger` آخر في المشروع لا يجد معالجًا في
سلسلته فيسقط على `logging.lastResort` — stderr، عتبة WARNING، بلا تنسيق.
عمليًا: `logger.info` في الـbackend الافتراضي للإشعارات كان يختفي تمامًا.

أربعة قرارات:

**١. مُسجِّل root.** فأي `getLogger("أي اسم")` يعمل فورًا بلا تسجيله هنا.
هذا يعني أنك تستطيع كتابة `logging.getLogger("matching")` في أي ملف غدًا
ويعمل — وهو شرط أن تُملأ الاثنا عشر تطبيقًا التي لا تحوي سطر تسجيل واحدًا.

**٢. ملفّ لكل عملية على ويندوز.** ثلاث نوافذ عندك تكتب معًا (Django،
Daphne، Celery). و`RotatingFileHandler` على ويندوز يحاول إعادة تسمية
الملفّ عند التدوير، وويندوز يمنع إعادة تسمية ملفّ مفتوح في عملية أخرى —
فيسقط التدوير بـPermissionError متكرّر. الحلّ أن يكتب كلٌّ في ملفّه.

**٣. الأخطاء في ملفّ مستقلّ.** `errors.log` يحوي WARNING فما فوق فقط.
حين يشتكي سائق، تفتح هذا الملفّ لا ملفًّا فيه مئة ألف سطر نبض GPS.

**٤. JSON للملفّات، نصّ للطرفية.** الطرفية تُقرأ بالعين الآن، والملفّ
تقرؤه أداة غدًا. وإعادة تحليل نصّ حرّ لاحقًا أصعب من كتابته منظَّمًا.
"""
import os
import sys
from pathlib import Path


def _stream_name():
    """
    اسم مميّز للعملية الحالية، ليكتب كلٌّ في ملفّه.

    يمكن تثبيته صراحةً بمتغيّر البيئة LOG_STREAM، وإلّا يُستنتج من سطر
    الأوامر: manage.py runserver → "web"، daphne → "ws"، celery → "celery".
    """
    explicit = os.environ.get("LOG_STREAM", "").strip()

    if explicit:
        return explicit

    argv = " ".join(sys.argv).lower()

    if "daphne" in argv:
        return "ws"
    if "celery" in argv:
        return "beat" if " beat" in argv else "celery"
    if "runserver" in argv:
        return "web"
    if "manage.py" in argv:
        # أمر إداري: اسم الأمر نفسه، فلا تختلط مخرجات الاختبارات بالخادم
        for arg in sys.argv[1:]:
            if not arg.startswith("-"):
                return f"cmd-{arg}"[:40]
        return "cmd"

    return "app"


def build_logging(base_dir, debug=False):
    log_dir = Path(base_dir) / "logs"
    log_dir.mkdir(exist_ok=True)

    stream = _stream_name()

    app_file = log_dir / f"{stream}.log"
    error_file = log_dir / f"{stream}.errors.log"

    console_level = "INFO" if debug else "WARNING"

    return {
        "version": 1,
        "disable_existing_loggers": False,

        "filters": {
            "request_context": {
                "()": "config.observability.filters.RequestContextFilter",
            },
        },

        "formatters": {
            # الطرفية: مضغوط ومقروء. المعرّف أولًا لأنه ما تنسخه للبحث.
            "console": {
                "format": "{asctime} {request_id:>12} {levelname:<7} {name:<18} {message}",
                "datefmt": "%H:%M:%S",
                "style": "{",
            },
            "json": {
                "()": "config.observability.filters.JSONFormatter",
            },
        },

        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
                "filters": ["request_context"],
                "level": console_level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(app_file),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
                "formatter": "json",
                "filters": ["request_context"],
                "level": "INFO",
                "delay": True,
            },
            "errors": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(error_file),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 10,
                "encoding": "utf-8",
                "formatter": "json",
                "filters": ["request_context"],
                "level": "WARNING",
                "delay": True,
            },
        },

        # كل مُسجِّل في المشروع، مسمّى أو غير مسمّى، يمرّ من هنا.
        "root": {
            "handlers": ["console", "file", "errors"],
            "level": "INFO",
        },

        "loggers": {
            # مُسجِّل الطلبات: يكتب سطرًا لكل طلب. مفيد جدًا وثرثار جدًا،
            # فيبقى في الملفّ ولا يملأ الطرفية إلا في وضع التطوير.
            "http": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False,
            },

            # django.request يسجّل استثناءات الـviews. نُبقيه لكن نمنع
            # الازدواج مع معالجنا الذي يسجّل الشيء نفسه بتفصيل أوفى.
            "django.request": {
                "handlers": ["errors", "file"],
                "level": "ERROR",
                "propagate": False,
            },

            # استعلامات SQL: صامتة إلا حين تطلبها صراحةً.
            "django.db.backends": {
                "handlers": ["console"],
                "level": os.environ.get("SQL_LOG_LEVEL", "WARNING"),
                "propagate": False,
            },

            "daphne": {"handlers": ["file"], "level": "INFO", "propagate": False},
        },
    }
