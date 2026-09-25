import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

DEPLOYMENT_ENV = env("DEPLOYMENT_ENV", default="development").lower()
SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost", "testserver"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if DEPLOYMENT_ENV == "production":
    if DEBUG or SECRET_KEY.startswith("django-insecure-") or len(SECRET_KEY) < 50 or not ALLOWED_HOSTS:
        raise ImproperlyConfigured("Production requires DEBUG=False, a strong SECRET_KEY, and ALLOWED_HOSTS.")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # GeoDjango
    "django.contrib.gis",

    # API
    "rest_framework",
    "rest_framework.authtoken",
    "channels",
    "drf_spectacular",
    "drf_spectacular_sidecar",

    # Local apps
    "users",
    "health",
    "drivers",
    "vehicles",
    "maps",
    "rides",
    "pricing",
    "matching",
    "presence",
    "realtime",
    "locations",
    # الخدمات والميزات التي يشغّلها المشغّل ويطفئها من الأدمن.
    "catalog",
    # أدوات النموّ: العمولات، العروض، الحوافز، التقارير.
    "growth",
    "ads",
    "trips",
    "feedback",
    "notifications",
    "ops",
    "payments",
    # كشف الغش والتلاعب: إشارات، نقاط خطر، قضايا مراجعة.
    "integrity",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'config.security.AdminIPAllowlistMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'config.observability.middleware.RequestContextMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = "config.asgi.application"

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }
# -----------------------------------------------------------------
# قاعدة البيانات — مع تجمّع اتصالات حقيقي
#
# بدون التجمّع يفتح جانغو اتصالًا جديدًا لكلّ طلب ويغلقه بعده. تحت حمل
# متزامن يعني ذلك أمرين معًا: كلفة مصافحة TCP+TLS في كلّ طلب، ونفاد
# `max_connections` في PostgreSQL. قيس ذلك في هذا المشروع فعليًّا:
# ثمانون مستخدمًا متزامنًا ← 1013 خطأ "sorry, too many clients already"
# وHTTP 500 على كلّ نقطة نهاية بما فيها GET /auth/me/.
#
# الحدّ الأقصى للتجمّع × عدد العمليّات يجب أن يبقى تحت max_connections:
#   web (daphne) + celery + beat ≈ 3 عمليّات × DB_POOL_MAX + احتياطي
# راجع تعليق max_connections في compose.dev.yaml
# -----------------------------------------------------------------
DB_POOL_MIN = env.int("DB_POOL_MIN", default=2)
DB_POOL_MAX = env.int("DB_POOL_MAX", default=20)

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
        "OPTIONS": {
            "pool": {
                "min_size": DB_POOL_MIN,
                "max_size": DB_POOL_MAX,
                # انتظار اتصال من التجمّع. أقصر من مهلة الطلب عمدًا:
                # فشلٌ سريع بـ500 مفهوم أفضل من طلب معلّق دقيقة كاملة.
                "timeout": env.float("DB_POOL_TIMEOUT", default=10.0),
                # يُغلق الاتصال الخامل بعد هذه المدّة فلا تتراكم اتصالات
                # ميتة بعد موجة حمل.
                "max_idle": env.float("DB_POOL_MAX_IDLE", default=300.0),
            },
        },
        # اتصال قُطع من طرف الخادم (إعادة تشغيل، pgbouncer) يُكتشف قبل
        # استعماله بدل أن يُسقط أوّل طلب يقع عليه.
        "CONN_HEALTH_CHECKS": True,
    }
}

# لا تجمّع مع CONN_MAX_AGE: التجمّع نفسه هو ما يبقي الاتصالات حيّة،
# وضبط الاثنين معًا يرفض جانغو الإقلاع به صراحةً.
CONN_MAX_AGE = 0


AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# هل يخدم خادم ASGI نفسه /static/؟
# نعم في التطوير (وإلا انكسرت واجهة Swagger تحت daphne)، ولا في الإنتاج
# حيث يخدمها Nginx من مجلّد staticfiles/ المُجمَّع.
SERVE_STATIC_FILES = env.bool("SERVE_STATIC_FILES", default=DEBUG)

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# مسار Nginx الداخلي لتسليم الوسائط عبر X-Accel-Redirect بعد فحص
# الصلاحية في جانغو. اتركه فارغًا في التطوير (بلا Nginx) فيخدم جانغو
# الملفّ بنفسه. راجع drivers/views_media.py و docker/nginx.conf
MEDIA_INTERNAL_PREFIX = env("MEDIA_INTERNAL_PREFIX", default="")

# سقف حجم وثيقة السائق. صورة رخصة لا فيلم.
MAX_DOCUMENT_BYTES = env.int("MAX_DOCUMENT_BYTES", default=8 * 1024 * 1024)
# عدد الوسطاء الموثوقين أمام التطبيق (Nginx = 1، Nginx خلف CDN = 2).
#
# يحسم كيف يُقرأ X-Forwarded-For. الترويسة مسلسلة `client, p1, p2` وأوّل
# عنصر فيها **يكتبه العميل**، فأخذُه يجعل كلّ حدّ يعتمد على الـIP قابلًا
# للتجاوز بترويسة واحدة. نعدّ من الآخر بمقدار هذا الرقم.
# صفر = لا وسيط: تُتجاهل الترويسة ويُؤخذ REMOTE_ADDR.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)

USE_X_FORWARDED_PROTO = env.bool("USE_X_FORWARDED_PROTO", default=False)
if USE_X_FORWARDED_PROTO:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=DEPLOYMENT_ENV == "production")
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000 if DEPLOYMENT_ENV == "production" else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=DEPLOYMENT_ENV == "production")
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=DEPLOYMENT_ENV == "production")
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=DEPLOYMENT_ENV == "production")
SESSION_COOKIE_HTTPONLY = True

# --- ضوابط config/security.py ---
# عمر توكن الدخول بالأيام؛ الصفر يطفئه. 90 يومًا: سائقٌ يعمل يوميًّا يعيد
# الدخول برمز مرّة كلّ ثلاثة أشهر، وهاتفٌ مسروق لا يبقى داخلًا إلى الأبد.
AUTH_TOKEN_TTL_DAYS = env.int("AUTH_TOKEN_TTL_DAYS", default=90)
LOCATION_MAX_PLAUSIBLE_SPEED_KMH = env.float("LOCATION_MAX_PLAUSIBLE_SPEED_KMH", default=200)
# مسار لوحة Django — غيّره في الإنتاج: /admin/ أوّل ما تجرّبه البوتات.
ADMIN_URL = env("ADMIN_URL", default="admin/").strip("/") + "/"
# فارغة = بلا قيد. مثال: ADMIN_ALLOWED_IPS=203.0.113.7,198.51.100.4
ADMIN_ALLOWED_IPS = env.list("ADMIN_ALLOWED_IPS", default=[])
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


REDIS_URL = env("REDIS_URL")


CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

CELERY_BEAT_SCHEDULE = {
    "evaluate-driver-incentives": {
        "task": "growth.tasks.evaluate_all_incentives",
        "schedule": 86400.0,   # شبكة أمان؛ الأساس بعد كلّ رحلة مكتملة
    },
    "materialize-ride-subscriptions": {
        "task": "rides.tasks.materialize_ride_subscriptions",
        "schedule": 300.0,   # كلّ 5 دقائق: الطلب يُنشأ قبل موعده بنصف ساعة
    },
    "expire-stale-offers": {
        "task": "matching.tasks.expire_stale_offers",
        "schedule": 15.0,  # كل 15 ثانية
    },
    "expire-stale-rides": {
        "task": "matching.tasks.expire_stale_rides",
        "schedule": 30.0,
    },
    "sweep-stale-driver-presence": {
            "task": "presence.tasks.sweep_stale_driver_presence",
            "schedule": 15.0,  # ثانية
    },
    "expire-stale-invitations": {
        "task": "matching.tasks.expire_stale_invitations",
        "schedule": 30.0,   # شبكة أمان فقط — الانتهاء الدقيق بمهمة مجدولة لكل دعوة
    },
    "cleanup-old-trip-locations": {
        "task": "trips.tasks.cleanup_old_trip_locations",
        "schedule": 3600.0,   # كل ساعة، دفعات صغيرة بدل جرف يومي ضخم
    },
    "escalate-stale-complaints": {
        "task": "feedback.tasks.escalate_stale_complaints",
        "schedule": 3600.0,
    },
    "recalculate-rating-summaries": {
        "task": "feedback.tasks.recalculate_rating_summaries",
        "schedule": 86400.0,   # شبكة أمان يومية لا مسار أساسي
    },
    "expire-stale-notifications": {
        "task": "notifications.tasks.expire_stale_notifications",
        "schedule": 60.0,      # كل دقيقة: مهلة الدعوة ثوانٍ لا ساعات
    },
    "retry-pending-notifications": {
        "task": "notifications.tasks.retry_pending_notifications",
        "schedule": 120.0,
    },
    "cleanup-old-notifications": {
        "task": "notifications.tasks.cleanup_old_notifications",
        "schedule": 86400.0,
    },
    # المدفوعات — شبكات أمان لا مسارات أساسية
    "backfill-missing-payments": {
        "task": "payments.tasks.backfill_missing_payments",
        "schedule": 300.0,     # كل 5 دقائق: رحلة مكتملة بلا دفعة انحراف يُصلَح بسرعة
    },
    "retry-stuck-payments": {
        "task": "payments.tasks.retry_stuck_payments",
        "schedule": 600.0,
    },
    "audit-ledger": {
        "task": "payments.tasks.audit_ledger",
        "schedule": 3600.0,    # يجب أن يعيد صفرًا دائمًا — أي رقم آخر حادثة
    },
    # كشف الغش: أنماط لا تُرى إلّا من تجميع أيّام (أجهزة، ثنائيّات، رحلات قصيرة).
    "integrity-detectors": {
        "task": "integrity.tasks.run_integrity_detectors",
        "schedule": 1800.0,
    },
    # التلاشي يحدث مع الوقت: من توقّف عن الغش يعود سليمًا وحده.
    "integrity-recompute": {
        "task": "integrity.tasks.recompute_risk_scores",
        "schedule": 21600.0,
    },
}
# settings.py
PRESENCE_REDIS_URL = env("PRESENCE_REDIS_URL", default=REDIS_URL)  # يمكن نفس REDIS_URL
PRESENCE_HEARTBEAT_FRESH_SECONDS = 30   # PRESENT
PRESENCE_HEARTBEAT_STALE_SECONDS = 60   # بعدها OFFLINE تلقائيًا


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                    {
                        "address": env("REDIS_URL"),
                        "socket_timeout": 120,
                        "socket_connect_timeout": 10,
                    }
                ],
            "capacity": 1500,
            "expiry": 180,
        },
    },
}


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}

# الاختبارات تعمل على قاعدة بيانات مؤقّتة لكنّها كانت تكتب في كاش Redis
# **المشترك** مع الخادم الحيّ: `LocationService` خزّن مناطق قاعدة الاختبار
# (بمعرّفاتها) فردّ الخادم الحيّ بعدها 500 على كلّ طلب رحلة:
#     Key (service_area_id)=(3) is not present in table locations_servicearea
# ذاكرة العملية وحدها للاختبارات — لا تسرّب في الاتّجاهين.
if "test" in sys.argv or "pytest" in sys.modules:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "soum-tests",
        }
    }

# otp
OTP_TTL_SECONDS = env.int("OTP_TTL_SECONDS", default=300)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)

# الهاتف: 3 طلبات خلال 10 دقائق.
OTP_RATE_PHONE_LIMIT = env.int("OTP_RATE_PHONE_LIMIT", default=3)
OTP_RATE_PHONE_WINDOW = env.int("OTP_RATE_PHONE_WINDOW", default=600)
# الجهاز: 5 طلبات خلال 10 دقائق.
OTP_RATE_DEVICE_LIMIT = env.int("OTP_RATE_DEVICE_LIMIT", default=5)
OTP_RATE_DEVICE_WINDOW = env.int("OTP_RATE_DEVICE_WINDOW", default=600)
# IP: 10 طلبات خلال 10 دقائق.
OTP_RATE_IP_LIMIT = env.int("OTP_RATE_IP_LIMIT", default=10)
OTP_RATE_IP_WINDOW = env.int("OTP_RATE_IP_WINDOW", default=600)

MATCHING_SHARED_ENABLED = True
MATCHING_SHARED_STRATEGY = "heuristic"          # لاحقًا: "routing_engine"
MATCHING_SHARED_JOIN_RADIUS_KM = 3.0            # أقصى مسافة بين نقطتي الالتقاط
MATCHING_SHARED_MAX_DEST_DISTANCE_KM = 5.0      # أقصى مسافة بين الوجهتين
MATCHING_SHARED_MIN_SCORE = 55                  # أقل نقاط توافق مقبولة (من 100)
MATCHING_SHARED_SHOW_GENDER = True              # إظهار جنس الركاب الحاليين للمرشح
MATCHING_SHARED_REQUIRE_DRIVER_CONFIRMATION = False  # لو True: السائق لازم يأكد الراكب الجديد
MATCHING_SHARED_JOIN_TTL_SECONDS = 45           # مهلة قبول الانضمام
MATCHING_SHARED_MAX_GROUP_SEATS = 4

MATCHING_SHARED_SCHEDULED_PICKUP_RADIUS_KM = 10
MATCHING_SHARED_SCHEDULED_DEST_RADIUS_KM = 15
MATCHING_SHARED_SCHEDULED_TIME_WINDOW_MINUTES = 60
MATCHING_SHARED_SCHEDULED_MIN_SCORE = 60


# اعدادات الرحلات من حيث عدد السائقين الذين سيقدمون عرضا
MATCHING_RADII_KM = {
    "fast": 5,
    "express": 5,
    "standard": 7,
    "saving": 10,
    "shared": 8,
    "scheduled": 15,
}

MATCHING_NORMAL_DRIVER_LIMIT = env.int(
    "MATCHING_NORMAL_DRIVER_LIMIT",
    default=10,
)

MATCHING_MARKETPLACE_DRIVER_LIMIT = env.int(
    "MATCHING_MARKETPLACE_DRIVER_LIMIT",
    default=40,
)

MATCHING_NORMAL_RADIUS_KM = env.float(
    "MATCHING_NORMAL_RADIUS_KM",
    default=5,
)

MATCHING_MARKETPLACE_RADIUS_KM = env.float(
    "MATCHING_MARKETPLACE_RADIUS_KM",
    default=10,
)

RIDE_OFFER_TTL_SECONDS = env.int(
    "RIDE_OFFER_TTL_SECONDS",
    default=30,
)

# مهلة تهدئة بعد رفض السائق: تمنع الزبون من إعادة دعوة السائق نفسه فورًا.
# اجعلها 0 لتعطيلها.
RIDE_INVITATION_REJECT_COOLDOWN_SECONDS = env.int(
    "RIDE_INVITATION_REJECT_COOLDOWN_SECONDS",
    default=60,
)


# -----------------------------------------------------------------
# دورة حياة الرحلة
# -----------------------------------------------------------------

# نصف قطر تسجيل الوصول. ضيّق عمدًا: وصول كاذب من بعيد يبدأ عدّاد عدم حضور
# الزبون، وهو مدخل احتيال حقيقي لا مجرد خطأ.
TRIP_ARRIVAL_RADIUS_M = env.int("TRIP_ARRIVAL_RADIUS_M", default=200)

# أوسع: الوجهة قد تتغيّر قليلًا أثناء الرحلة بطلب الراكب، وهذا مشروع.
TRIP_DROPOFF_RADIUS_M = env.int("TRIP_DROPOFF_RADIUS_M", default=300)

# خنق تسجيل المسار: بدونه سائق واقف في زحمة عشر دقائق يكتب 120 صفًا لنقطة واحدة.
TRIP_LOCATION_MIN_INTERVAL_SECONDS = env.int(
    "TRIP_LOCATION_MIN_INTERVAL_SECONDS", default=5
)
TRIP_LOCATION_MIN_DISTANCE_M = env.int("TRIP_LOCATION_MIN_DISTANCE_M", default=30)

# §17 في الوثيقة: "الموقع الخام لا يجب أن يبقى إلى الأبد."
TRIP_LOCATION_RETENTION_DAYS = env.int("TRIP_LOCATION_RETENTION_DAYS", default=30)



# -----------------------------------------------------------------
# التقييم والشكاوى
# -----------------------------------------------------------------

# مهلة التقييم. بعدها ينكشف تقييم الطرف الآخر ويُقفل باب التقييم:
# تقييم يصل بعد شهرين لا يقيس تجربة بل مزاجًا.
RATING_WINDOW_DAYS = env.int("RATING_WINDOW_DAYS", default=14)

# تحت هذه الدرجة يصير السبب إلزاميًا (وسم أو تعليق). نجمة واحدة بلا سبب
# لا تُصلح شيئًا ولا تدخل في أي قرار.
RATING_COMMENT_REQUIRED_BELOW = env.int("RATING_COMMENT_REQUIRED_BELOW", default=3)

# مهلة فتح شكوى بعد الرحلة. أطول من مهلة التقييم عمدًا: المشكلة قد
# تتكشّف متأخرة (خصم مالي، غرض منسيّ).
COMPLAINT_WINDOW_DAYS = env.int("COMPLAINT_WINDOW_DAYS", default=30)

# شكوى مفتوحة أطول من هذا بلا حراك تُصعَّد تلقائيًا.
COMPLAINT_ESCALATE_AFTER_HOURS = env.int("COMPLAINT_ESCALATE_AFTER_HOURS", default=48)


# -----------------------------------------------------------------
# الإشعارات
# -----------------------------------------------------------------

# الافتراضي هو الطابعة لا FCM، عمدًا: بيئة تطوير تُرسل إشعارات حقيقية
# إلى هواتف الناس خطأٌ يُكتشف متأخرًا جدًا.
NOTIFICATION_BACKEND = env(
    "NOTIFICATION_BACKEND",
    default="notifications.backends.console.ConsoleBackend",
)

NOTIFICATION_MAX_ATTEMPTS = env.int("NOTIFICATION_MAX_ATTEMPTS", default=3)

# -----------------------------------------------------------------
# القناة الاحتياطية (رسالة نصّية) — §10 في الوثيقة
#
# معطّلة افتراضيًا عمدًا. الرسائل مدفوعة، وقناةٌ مدفوعة تُفتح على
# مصراعيها تصير فاتورة قبل أن تصير خدمة. تُفعَّل بعد الاشتراك بمزوّد
# وضبط OTP_DELIVERY_BACKEND عليه.
#
# ثلاثة شروط مجتمعة قبل أن تُرسَل رسالة: الإشعار عاجل، والدفع لم يصل،
# والحدث في القائمة البيضاء أدناه. راجع notifications/services/fallback.py
# -----------------------------------------------------------------
NOTIFICATION_SMS_FALLBACK = env.bool("NOTIFICATION_SMS_FALLBACK", default=False)

NOTIFICATION_SMS_FALLBACK_EVENTS = env.list(
    "NOTIFICATION_SMS_FALLBACK_EVENTS",
    default=[
        "invitation.sent",
        "offer.accepted",
        "driver.arrived",
        "trip.started",
        "ride.cancelled_by_driver",
    ],
)

# رسالة واحدة لكلّ (مستخدم، حدث) خلال هذه المدّة. سائقٌ تصله عشر دعوات
# في دقيقة يجب ألّا تصله عشر رسائل.
NOTIFICATION_SMS_FALLBACK_COOLDOWN = env.int(
    "NOTIFICATION_SMS_FALLBACK_COOLDOWN", default=300
)

# للإنتاج: بدّل NOTIFICATION_BACKEND إلى
# "notifications.backends.fcm.FCMBackend" واضبط الاثنين أدناه.
FCM_PROJECT_ID = env("FCM_PROJECT_ID", default="")
FCM_SERVICE_ACCOUNT_FILE = env("FCM_SERVICE_ACCOUNT_FILE", default="")
# بديل الملفّ للاستضافة السحابيّة: محتوى JSON نفسه أو Base64 له. يغني عن
# FCM_PROJECT_ID لأنّ الملفّ يحمل project_id. لا تضعه في الريبو أبدًا.
FCM_SERVICE_ACCOUNT_JSON = env("FCM_SERVICE_ACCOUNT_JSON", default="")


# -----------------------------------------------------------------
# قنوات الإشعار
#
# الترتيب هنا هو ترتيب المحاولة الافتراضي حين لا يضبط المستخدم تفضيلاته،
# وأوّل قناة تُسلّم توقف السلسلة. إضافة قناة جديدة (واتساب حين يُتاح، بريد،
# مكالمة آلية) سطرٌ هنا وملفّ في notifications/channels/ — ولا شيء ثالث.
# -----------------------------------------------------------------
NOTIFICATION_CHANNELS = env.list(
    "NOTIFICATION_CHANNELS",
    default=[
        "notifications.channels.push.PushChannel",
        "notifications.channels.telegram.TelegramChannel",
        "notifications.channels.sms.SmsChannel",
    ],
)

# -----------------------------------------------------------------
# تليغرام
#
# اخترناه على واتساب لسببين عمليّين: واتساب Business API يحتاج حساب أعمال
# موثَّقًا ومزوّدًا معتمدًا وقوالب مراجَعة ويُحاسَب بالمحادثة، ولا يُتاح
# عمليًّا هنا. وتليغرام بوتٌ يُنشأ في دقيقتين ونداء HTTP واحد.
#
# التفعيل: أنشئ بوتًا عبر @BotFather، وضع الرمز واسم المستخدم أدناه، ثمّ
# اضبط الـwebhook على /api/v1/notifications/webhooks/telegram/ مع
# secret_token يطابق TELEGRAM_WEBHOOK_SECRET.
#
# بلا رمز تبقى القناة غير مهيّأة فتُتخطّى بصمت — لا تُسقط إشعارًا واحدًا.
# -----------------------------------------------------------------
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", default="")
TELEGRAM_WEBHOOK_SECRET = env("TELEGRAM_WEBHOOK_SECRET", default="")
TELEGRAM_TIMEOUT_SECONDS = env.float("TELEGRAM_TIMEOUT_SECONDS", default=8.0)

# رمز الربط لمرّة واحدة: قصير العمر لأنّه يمرّ عبر محادثة، ومن يلتقطه
# يربط حسابه بإشعارات غيره.
TELEGRAM_LINK_TTL_SECONDS = env.int("TELEGRAM_LINK_TTL_SECONDS", default=600)



REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # نسخة تسمّي الفاعل في سياق الحادثة لحظة نجاح المصادقة، فيُنسب
        # كلّ انتقال حالة إلى فاعله بدل "system". راجع config/observability/auth.py
        "config.observability.auth.ContextTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # الخوانق كانت معرَّفة بلا أصناف تُفعّلها — أي بلا أثر إطلاقًا.
    # راجع config/throttling.py
    "DEFAULT_THROTTLE_CLASSES": [
        "config.throttling.TrustedAnonThrottle",
        "config.throttling.TrustedUserThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "route_test": "30/min",
        # الحدّ العامّ. سخيّ عمدًا: تطبيق يفتح شاشة الرحلة يطلب أربع نقاط
        # دفعةً واحدة، وخنقُه يكسر الاستعمال العادي قبل أن يوقف مسيئًا.
        "user": env("THROTTLE_USER", default="1200/hour"),
        "anon": env("THROTTLE_ANON", default="120/hour"),
        # مشدَّدة: كلّ رمز يكلّف رسالة مدفوعة.
        "otp_request": env("THROTTLE_OTP_REQUEST", default="20/hour"),
        # تخمين رمز من ستّ خانات يمنح توكن مصادقة عند النجاح.
        "otp_verify": env("THROTTLE_OTP_VERIFY", default="30/hour"),
        # كتابات تُنشئ صفوفًا وتستدعي مزوّدًا خارجيًّا.
        "write": env("THROTTLE_WRITE", default="300/hour"),
    },
    "DEFAULT_SCHEMA_CLASS": (
        "drf_spectacular.openapi.AutoSchema"
    ),
    "EXCEPTION_HANDLER": (
        "config.observability.exception_handler.api_exception_handler"
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Modern Taxi API",
    "DESCRIPTION": (
        "OpenAPI documentation for the Modern Taxi platform."
    ),
    "VERSION": "1.0.0",

    "SERVE_INCLUDE_SCHEMA": False,

    # مهم مع request serializers وخصوصًا FileField.
    "COMPONENT_SPLIT_REQUEST": True,

    # أسماء صريحة للتعدادات المتصادمة.
    #
    # حقول كثيرة اسمها `status` أو `type`، ولكلٍّ مجموعة خيارات مختلفة.
    # بلا هذه الخريطة يخترع drf-spectacular أسماء مثل `Status0c9Enum`
    # و`TypefEnum` — صحيحة تقنيًّا، لكنّ مولّد عميل الموبايل يُنتج منها
    # أصنافًا بأسماء لا معنى لها، وتتغيّر عشوائيًّا مع أيّ إضافة حقل.
    # مبرمج التطبيق يستحقّ `RideStatusEnum` لا `Status0c9Enum`.
    "ENUM_NAME_OVERRIDES": {
        "RideStatusEnum": "rides.models.RideStatus.choices",
        "RideModeEnum": "rides.models.RideMode.choices",
        "TripCategoryEnum": "rides.models.TripCategory.choices",
        "TripStatusEnum": "trips.models.TripStatus.choices",
        "OfferStatusEnum": "matching.models.OfferStatus.choices",
        "InvitationStatusEnum": "matching.models.InvitationStatus.choices",
        "PaymentStatusEnum": "payments.models.PaymentStatus.choices",
        "DocumentTypeEnum": "drivers.models.DocumentType.choices",
        "DocumentStatusEnum": "drivers.models.DocumentStatus.choices",
        "UserRoleEnum": "users.models.UserRole.choices",
        "NotificationStatusEnum": "notifications.models.NotificationStatus.choices",
        "AuditEntityEnum": "ops.models.AuditEntity.choices",
        "AuditActionEnum": "ops.models.AuditAction.choices",
        "ComplaintStatusEnum": "feedback.models.ComplaintStatus.choices",
        "ComplaintCategoryEnum": "feedback.models.ComplaintCategory.choices",
        "ComplaintSeverityEnum": "feedback.models.ComplaintSeverity.choices",
        "RefundStatusEnum": "payments.models.RefundStatus.choices",
    },

    "SORT_OPERATIONS": True,
"SORT_OPERATION_PARAMETERS": True,
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",

    "TAGS": [
        {
            "name": "Authentication",
            "description": (
                "OTP authentication and user session endpoints."
            ),
        },
        {
            "name": "Users",
            "description": (
                "Authenticated user endpoints."
            ),
        },
        {
            "name": "Drivers",
            "description": (
                "Driver onboarding, documents and availability."
            ),
        },
        {
            "name": "Driver Administration",
            "description": (
                "Administrative driver verification operations."
            ),
        },
        {
            "name": "Vehicles",
            "description": (
                "Driver vehicle management."
            ),
        },
        {
            "name": "Rides",
            "description": (
                "Customer ride requests and cancellation."
            ),
        },
        {
            "name": "Matching",
            "description": (
                "Driver offers and customer offer selection."
            ),
        },
        {
            "name": "Shared Rides",
            "description": (
                "Instant shared ride operations."
            ),
        },
        {
            "name": "Scheduled Shared Trips",
            "description": (
                "Scheduled shared trip operations."
            ),
        },
        {
            "name": "Published Trips",
            "description": (
                "Intercity, service-line and recreational trips."
            ),
        },
        {
            "name": "Maps",
            "description": (
                "Routing and map services."
            ),
        },
        {
            "name": "Payments",
            "description": (
                "Trip payments, gateways, refunds and driver balances."
            ),
        },
    ],
}

# الإنتاج: التوثيق والمخطّط للإدارة وحدها. خريطةٌ كاملة لكلّ نقطة ومعاملاتها
# هديّةٌ لمن يبحث عن ثغرة.
if DEPLOYMENT_ENV == "production":
    SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = ["rest_framework.permissions.IsAdminUser"]

MATCHING_LOCATION_MAX_AGE_SECONDS = env.int(
    "MATCHING_LOCATION_MAX_AGE_SECONDS",
    default=60,
)

GDAL_LIBRARY_PATH = env("GDAL_LIBRARY_PATH", default=None)
GEOS_LIBRARY_PATH = env("GEOS_LIBRARY_PATH", default=None)

MAPS_ROUTING_ENABLED = env.bool("MAPS_ROUTING_ENABLED", default=True)
MAPS_ROUTING_REQUIRED = env.bool("MAPS_ROUTING_REQUIRED", default=True)
MAPS_ROUTING_BASE_URL = env("MAPS_ROUTING_BASE_URL", default="https://router.project-osrm.org")
MAPS_ROUTING_TIMEOUT_SECONDS = env.int("MAPS_ROUTING_TIMEOUT_SECONDS", default=10)

# قاطع دورة مزوّد التوجيه: بعد هذا العدد من الإخفاقات المتتالية نتوقّف
# عن سؤاله لهذه المدّة ونقدّر داخليًّا. بدونه يصير كلّ طلب انتظارًا
# لمهلة الشبكة، فيعمل النظام على بطء المزوّد لا على منطقه.
MAPS_ROUTING_BREAKER_THRESHOLD = env.int("MAPS_ROUTING_BREAKER_THRESHOLD", default=3)
MAPS_ROUTING_BREAKER_COOLDOWN = env.int("MAPS_ROUTING_BREAKER_COOLDOWN", default=60)

# معايرة التقدير الداخلي حين يتعذّر المزوّد. تُتجاوَز لكلّ منطقة خدمة
# عبر ServiceArea.road_detour_factor و average_speed_kmh.
MAPS_ROAD_DETOUR_FACTOR = env.float("MAPS_ROAD_DETOUR_FACTOR", default=1.35)
MAPS_AVERAGE_SPEED_KMH = env.float("MAPS_AVERAGE_SPEED_KMH", default=30.0)
MAPS_USER_AGENT = env("MAPS_USER_AGENT", default="RidesApp/1.0 (contact: ops@example.com)")
OTP_DELIVERY_BACKEND = env("OTP_DELIVERY_BACKEND", default="console")
if DEPLOYMENT_ENV == "production" and OTP_DELIVERY_BACKEND in (
    "console",
    "users.services.delivery.console.ConsoleOTPBackend",
):
    raise ImproperlyConfigured("Configure a real OTP_DELIVERY_BACKEND in production.")

# مزوّد الرسائل حين OTP_DELIVERY_BACKEND = "sms" أو صنف يرث HTTPSMSBackend.
SMS_ENDPOINT = env("SMS_ENDPOINT", default="")
SMS_API_KEY = env("SMS_API_KEY", default="")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="")


# -----------------------------------------------------------------
# النزاهة (كشف الغش) — راجع integrity/
# -----------------------------------------------------------------
# عمر النصف لوزن الإشارة: بعده تساوي نصف وزنها.
INTEGRITY_HALF_LIFE_DAYS = env.float("INTEGRITY_HALF_LIFE_DAYS", default=14)
# حدود المستويات بالنقاط (0–100). التقييد الآليّ لا يتجاوز «مقيّد» أبدًا:
# لا حظر بلا إنسان.
INTEGRITY_LEVEL_THRESHOLDS = {
    "watch": env.int("INTEGRITY_WATCH_AT", default=20),
    "review": env.int("INTEGRITY_REVIEW_AT", default=40),
    "restricted": env.int("INTEGRITY_RESTRICT_AT", default=70),
}
# False = النظام يلاحظ ويفتح قضايا فقط، والتقييد قرار موظّف.
INTEGRITY_AUTO_RESTRICT = env.bool("INTEGRITY_AUTO_RESTRICT", default=True)
# موقعٌ أعلن أندرويد أنّه مُحاكى (تطبيق Fake GPS) لا يُكتب ولا يُبثّ.
INTEGRITY_REJECT_MOCK_LOCATIONS = env.bool("INTEGRITY_REJECT_MOCK_LOCATIONS", default=True)


# -----------------------------------------------------------------
# المدفوعات
# -----------------------------------------------------------------
#
# إضافة بوابة جديدة = ملفّ في payments/gateways/ + سطر هنا.
# لا ترحيل قاعدة بيانات، ولا تعديل نماذج، ولا شرط جديد في الخدمات.
#
# مثال عند فتح مزوّد للسوق:
#     "payments.gateways.paymob.PaymobGateway",
#
PAYMENT_GATEWAYS = env.list(
    "PAYMENT_GATEWAYS",
    default=["payments.gateways.cash.CashGateway"],
)

PAYMENT_DEFAULT_GATEWAY = env("PAYMENT_DEFAULT_GATEWAY", default="cash")

from config.logging_config import build_logging

LOGGING = build_logging(BASE_DIR, debug=DEBUG)