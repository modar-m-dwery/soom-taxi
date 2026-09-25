import redis
from django.conf import settings

# connection pool مستقل حتى لا يتشارك presence نفس pool مع Channels/Celery broker
# بدون قصد ويسبب تنافس اتصالات لاحقًا. لو ما فيه PRESENCE_REDIS_URL خاص،
# نرجع لنفس REDIS_URL العام المستخدم في المشروع.
_pool = redis.ConnectionPool.from_url(
    getattr(settings, "PRESENCE_REDIS_URL", getattr(settings, "REDIS_URL", "redis://localhost:6379/0")),
    decode_responses=True,
)


def get_redis():
    return redis.Redis(connection_pool=_pool)
