#!/usr/bin/env bash
# ---------------------------------------------------------------
# الاستعادة — سوم تاكسي
#
# نسخةٌ لم تُختبر استعادتها ليست نسخة احتياطية بل ملفّ يبعث الطمأنينة.
# هذا السكربت هو الاختبار، ويُشغَّل على قاعدة **جديدة** لا على الحيّة:
#
#     docker compose -f compose.dev.yaml run --rm \
#         -e RESTORE_TARGET_DB=taxi_restore_check \
#         backup /usr/local/bin/restore.sh /backups/<الملف>.dump
#
# الاستعادة فوق قاعدة الإنتاج تحتاج --force صريحة، لأنّ استعادة خاطئة
# تمحو ما تحاول إنقاذه.
# ---------------------------------------------------------------
set -euo pipefail

DUMP="${1:-}"
FORCE="${2:-}"

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
SOURCE_DB="${DB_NAME:-taxi_backend}"
TARGET_DB="${RESTORE_TARGET_DB:-${SOURCE_DB}_restore_check}"

if [ -z "$DUMP" ]; then
    echo "الاستعمال: restore.sh <ملفّ .dump> [--force]" >&2
    echo "" >&2
    echo "النسخ المتاحة:" >&2
    ls -1t /backups/*.dump 2>/dev/null | head -10 >&2 || echo "  (لا شيء)" >&2
    exit 2
fi

if [ ! -f "$DUMP" ]; then
    echo "✗ لا يوجد ملفّ: $DUMP" >&2
    exit 2
fi

if [ "$TARGET_DB" = "$SOURCE_DB" ] && [ "$FORCE" != "--force" ]; then
    echo "✗ الوجهة هي قاعدة العمل (${SOURCE_DB})." >&2
    echo "  استعِد إلى قاعدة جديدة، أو مرّر --force إن كنت متأكّدًا." >&2
    exit 2
fi

echo "[restore] المصدر : $DUMP"
echo "[restore] الوجهة : ${TARGET_DB}@${DB_HOST}"

export PGHOST="$DB_HOST" PGPORT="$DB_PORT" PGUSER="$DB_USER"

# قاعدة نظيفة: استعادة فوق بقايا سابقة تُنتج خليطًا يبدو سليمًا
psql --dbname=postgres -v ON_ERROR_STOP=1 -c \
    "DROP DATABASE IF EXISTS \"${TARGET_DB}\";"
psql --dbname=postgres -v ON_ERROR_STOP=1 -c \
    "CREATE DATABASE \"${TARGET_DB}\";"

# PostGIS قبل البيانات: الجداول تحوي أعمدة geometry ولا تُنشأ بدونه
psql --dbname="$TARGET_DB" -v ON_ERROR_STOP=1 -c \
    "CREATE EXTENSION IF NOT EXISTS postgis;"

echo "[restore] الاستعادة ..."

# --no-owner  لأنّ الوجهة قد تختلف ملكيتها
# --jobs=4    توازٍ يقصّر زمن التوقّف، وهو ما يُقاس فعلًا في الحادثة
# لا نُوقف على أوّل خطأ: تحذيرات الامتدادات شائعة وغير قاتلة، والحكم
# النهائي يقع على العدّ أدناه لا على رمز خروج pg_restore.
set +e
pg_restore \
    --dbname="$TARGET_DB" \
    --no-owner \
    --jobs=4 \
    "$DUMP"
RESTORE_CODE=$?
set -e

echo "[restore] رمز pg_restore: ${RESTORE_CODE} (تحذيرات الامتدادات متوقّعة)"

# -----------------------------------------------------------------
# التحقّق: هل استُعيدت بيانات فعلًا؟
#
# `pg_restore` قد ينتهي بنجاح ويترك قاعدة فارغة. العدّ هو الجواب.
# -----------------------------------------------------------------
TABLES="$(psql --dbname="$TARGET_DB" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"

USERS="$(psql --dbname="$TARGET_DB" -tAc \
    "SELECT count(*) FROM users_user;" 2>/dev/null || echo 0)"

RIDES="$(psql --dbname="$TARGET_DB" -tAc \
    "SELECT count(*) FROM rides_riderequest;" 2>/dev/null || echo 0)"

MIGRATIONS="$(psql --dbname="$TARGET_DB" -tAc \
    "SELECT count(*) FROM django_migrations;" 2>/dev/null || echo 0)"

POSTGIS="$(psql --dbname="$TARGET_DB" -tAc \
    "SELECT PostGIS_Version();" 2>/dev/null || echo "غائب")"

echo ""
echo "──────────────────────────────────────────"
echo "  الجداول      : ${TABLES}"
echo "  المستخدمون   : ${USERS}"
echo "  طلبات الركوب : ${RIDES}"
echo "  الترحيلات    : ${MIGRATIONS}"
echo "  PostGIS      : ${POSTGIS}"
echo "──────────────────────────────────────────"

if [ "$TABLES" -lt 20 ] || [ "$MIGRATIONS" -lt 10 ]; then
    echo "✗ الاستعادة ناقصة." >&2
    exit 1
fi

echo "✓ الاستعادة سليمة ومُتحقَّق منها."

if [ "${RESTORE_KEEP:-0}" != "1" ] && [ "$TARGET_DB" != "$SOURCE_DB" ]; then
    psql --dbname=postgres -c "DROP DATABASE \"${TARGET_DB}\";" >/dev/null
    echo "  (حُذفت قاعدة الفحص. RESTORE_KEEP=1 للإبقاء عليها.)"
fi
