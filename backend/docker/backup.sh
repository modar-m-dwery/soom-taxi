#!/usr/bin/env bash
# ---------------------------------------------------------------
# نسخة احتياطية لقاعدة البيانات — سوم تاكسي
#
# `pg_dump` بصيغة custom (‎-Fc‎) لا نصًّا عاديًّا: مضغوطة، وتقبل
# الاستعادة الانتقائية لجدول واحد، وتُوازي الاستعادة على عدّة أنوية.
# النصّ العادي يستعيد الكلّ أو لا شيء، وحجمه أضعاف.
#
# يُشغَّل من حاوية `backup` في compose كلّ ليلة، أو يدويًّا:
#     docker compose -f compose.dev.yaml run --rm backup
# ---------------------------------------------------------------
set -euo pipefail

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-taxi_backend}"
DB_USER="${DB_USER:-postgres}"

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/${DB_NAME}-${STAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "[backup] ${DB_NAME}@${DB_HOST}:${DB_PORT} → ${TARGET}"

# -Fc صيغة مضغوطة قابلة للاستعادة الانتقائية
# --no-owner  لتُستعاد على خادم بمستخدم مختلف بلا تعديل
pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --file="$TARGET"

SIZE="$(du -h "$TARGET" | cut -f1)"

# -----------------------------------------------------------------
# التحقّق — الخطوة التي تُنسى دائمًا
#
# نسخة لا تُقرأ ليست نسخة. `pg_restore --list` يفكّ الفهرس ويتحقّق من
# سلامة البنية، فيكشف ملفًّا مبتورًا (قرص امتلأ في منتصف الكتابة) الآن
# لا بعد ستّة أشهر حين تحتاجه فعلًا.
# -----------------------------------------------------------------
TABLES="$(pg_restore --list "$TARGET" | grep -c 'TABLE DATA' || true)"

if [ "$TABLES" -lt 5 ]; then
    echo "[backup] ✗ النسخة تحوي ${TABLES} جدولًا فقط — مشبوهة. لا تُحذف القديم." >&2
    exit 1
fi

echo "[backup] ✓ ${SIZE}، ${TABLES} جدولًا، مقروءة."

# -----------------------------------------------------------------
# الاحتفاظ
#
# الحذف **بعد** التحقّق لا قبله: لو كانت الجديدة تالفة نكون قد حذفنا
# السليمة. الترتيب هنا هو الفرق بين سياسة احتفاظ وفقدان بيانات.
# -----------------------------------------------------------------
DELETED="$(find "$BACKUP_DIR" -name "${DB_NAME}-*.dump" -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)"

if [ "$DELETED" -gt 0 ]; then
    echo "[backup] حُذفت ${DELETED} نسخة أقدم من ${RETENTION_DAYS} يومًا."
fi

REMAINING="$(find "$BACKUP_DIR" -name "${DB_NAME}-*.dump" | wc -l)"
echo "[backup] النسخ المتاحة: ${REMAINING}"

# تحذير صريح: نسخة على القرص نفسه ليست نسخة احتياطية بالمعنى الكامل.
if [ "${BACKUP_OFFSITE_HINT:-1}" = "1" ]; then
    echo "[backup] تذكير: انسخ ${BACKUP_DIR} إلى وجهة خارج هذا المضيف."
fi
