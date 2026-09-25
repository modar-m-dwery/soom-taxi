#!/usr/bin/env bash
# ---------------------------------------------------------------
# نقطة الدخول المشتركة لكل الخدمات (web / celery / beat).
#
# ثلاث وظائف:
#   1. الانتظار حتى تجهز postgres وredis فعلًا — depends_on وحده يضمن
#      أن الحاوية "بدأت" لا أنها "جاهزة"، والفرق بينهما هو سبب أشهر
#      انهيار عند أول `docker compose up`.
#   2. تفعيل امتداد PostGIS + تشغيل migrate (للخدمة الرئيسية فقط).
#   3. تسليم التنفيذ إلى الأمر المطلوب عبر exec، ليصل SIGTERM للعملية
#      الحقيقية فيتوقف الحاوية بنظافة بدل قتلها بعد 10 ثوانٍ.
# ---------------------------------------------------------------
set -euo pipefail

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"

# REDIS_URL بصيغة redis://host:port/db
REDIS_HOST="$(python -c "
import os, urllib.parse as u
p = u.urlparse(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
print(p.hostname or 'redis')
")"
REDIS_PORT="$(python -c "
import os, urllib.parse as u
p = u.urlparse(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
print(p.port or 6379)
")"

wait_for() {
    local host="$1" port="$2" name="$3" tries=60
    echo "[entrypoint] بانتظار ${name} على ${host}:${port} ..."
    until nc -z "$host" "$port" 2>/dev/null; do
        tries=$((tries - 1))
        if [ "$tries" -le 0 ]; then
            echo "[entrypoint] ✗ ${name} لم يجهز خلال المهلة." >&2
            exit 1
        fi
        sleep 1
    done
    echo "[entrypoint] ✓ ${name} جاهز."
}

wait_for "$DB_HOST" "$DB_PORT" "PostgreSQL"
wait_for "$REDIS_HOST" "$REDIS_PORT" "Redis"

# الترحيلات تُشغَّل من خدمة واحدة فقط (RUN_MIGRATIONS=1 في compose على web)،
# فتشغيلها من ثلاث حاويات معًا يفتح سباقًا على جدول django_migrations.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "[entrypoint] تفعيل امتداد PostGIS ..."
    python - <<'PY'
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    c.execute("SELECT PostGIS_Version();")
    print("[entrypoint] ✓ PostGIS:", c.fetchone()[0])
PY

    echo "[entrypoint] تشغيل الترحيلات ..."
    python manage.py migrate --noinput

    if [ "${SEED_DEMO:-0}" = "1" ]; then
        echo "[entrypoint] زرع بيانات العرض ..."
        python manage.py seed_rating_tags || true
        python manage.py seed_mobile_demo || true
    fi
fi

echo "[entrypoint] التشغيل: $*"
exec "$@"
