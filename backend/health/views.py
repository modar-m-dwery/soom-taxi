import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from redis import Redis


_logger = logging.getLogger(__name__)


def health_check(request):
    health = {
        "status": "ok",
        "database": "unknown",
        "redis": "unknown",
    }

    # Check PostgreSQL
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        health["database"] = "ok"
        _logger.info("Health check: PostgreSQL OK")

    except Exception:
        health["database"] = "error"
        health["status"] = "error"

        _logger.exception("Health check: PostgreSQL ERROR")

    # Check Redis
    try:
        redis_client = Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )

        redis_client.ping()
        health["redis"] = "ok"
        _logger.info("Health check: Redis OK")

    except Exception:
        health["redis"] = "error"
        health["status"] = "error"

        _logger.exception("Health check: Redis ERROR")

    _logger.info(
        "Health check completed: status=%s",
        health["status"],
    )

    return JsonResponse(health)