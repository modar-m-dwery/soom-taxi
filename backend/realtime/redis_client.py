import redis
from django.conf import settings

_pool = redis.ConnectionPool.from_url(
    getattr(settings, "REALTIME_REDIS_URL", getattr(settings, "REDIS_URL", "redis://localhost:6379/0")),
    decode_responses=True,
)


def get_redis():
    return redis.Redis(connection_pool=_pool)