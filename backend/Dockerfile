# syntax=docker/dockerfile:1
# ---------------------------------------------------------------
# صورة الباك إند — سوم تاكسي
#
# مرحلتان: builder يبني العجلات (wheels) بأدوات الترجمة، وruntime
# يحتوي مكتبات التشغيل فقط. النتيجة صورة أصغر وبلا gcc في الإنتاج.
# ---------------------------------------------------------------

# =============== المرحلة 1: البناء ===============
FROM python:3.12-slim AS builder

# مرآة اختيارية لـpip. الافتراضي pypi.org، وتُمرَّر فقط حين تكون الشبكة
# خلف مرآة داخلية أو حاجب:
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple/
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# apt عبر HTTPS لا HTTP: أنظف أمنيًا، وشرطٌ لازم خلف أيّ بوابة خروج
# تسمح بـ443 وحدها — وهي الحالة الشائعة في الشبكات المؤسّسية.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list 2>/dev/null || true

# شهادات CA إضافية — المجلّد فارغ افتراضيًا فلا أثر له على شبكة عادية.
# يلزم فقط خلف بوّابة تفحص TLS وتوقّع الشهادات بنفسها، وبدونه يفشل apt
# وpip بـ"certificate verify failed". راجع docker/extra-ca/README.md
COPY docker/extra-ca/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates 2>/dev/null || true
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements.txt .
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        pip wheel --wheel-dir=/wheels -r requirements.txt \
            --index-url "$PIP_INDEX_URL" \
            ${PIP_TRUSTED_HOST:+--trusted-host "$PIP_TRUSTED_HOST"} ; \
    else \
        pip wheel --wheel-dir=/wheels -r requirements.txt ; \
    fi


# =============== المرحلة 2: التشغيل ===============
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

# مكتبات التشغيل فقط.
#   gdal-bin       → يجرّ معه libgdal + libgeos_c + libproj، وهي ما تبحث
#                    عنه GeoDjango. تسميتها ترقيميًا (libgdal32/34...)
#                    تتغيّر بين إصدارات ديبيان، لذلك لا نثبّتها بالاسم.
#   libpq5         → عميل PostgreSQL لـpsycopg
#   netcat-openbsd → انتظار جاهزية postgres/redis في entrypoint
#   curl           → HEALTHCHECK
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libpq5 \
        netcat-openbsd \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# مستخدم غير جذر
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/staticfiles /app/media /app/logs /app/run \
    && chown -R appuser:appuser /app

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY --chown=appuser:appuser . .

USER appuser

# ملفات Swagger UI الساكنة (drf-spectacular-sidecar) تُجمَّع وقت البناء.
# بدون هذه الخطوة تفتح /api/docs/ صفحة بيضاء، لأن daphne — على عكس
# runserver — لا يخدم /static/ إطلاقًا.
# نمرّر إعدادات وهمية لأن .env غير موجود وقت البناء (وهذا مقصود).
RUN SECRET_KEY=build-time-only-not-used \
    DEBUG=False \
    DEPLOYMENT_ENV=build \
    DB_NAME=x DB_USER=x DB_PASSWORD=x DB_HOST=x DB_PORT=5432 \
    REDIS_URL=redis://localhost:6379/0 \
    SECURE_SSL_REDIRECT=False \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=45s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health/ || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
