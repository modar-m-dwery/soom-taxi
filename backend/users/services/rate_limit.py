from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    retry_after: int


class RateLimitService:
    @staticmethod
    def _check(
        key: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """
        Redis-backed atomic rate limiter.

        The key is initialized with the requested TTL when it does not exist.
        Redis INCR atomically increments the counter.
        """

        cache.add(key, 0, timeout=window)

        count = cache.incr(key)

        return RateLimitResult(
            allowed=count <= limit,
            count=count,
            limit=limit,
            retry_after=window,
        )
    
    @classmethod
    def check_phone(cls, phone: str) -> RateLimitResult:
        key = f"otp:rate:phone:{phone}"

        return cls._check(
            key=key,
            limit=settings.OTP_RATE_PHONE_LIMIT,
            window=settings.OTP_RATE_PHONE_WINDOW,
        )

    @classmethod
    def check_device(cls, device_id: str) -> RateLimitResult:
        key = f"otp:rate:device:{device_id}"

        return cls._check(
            key=key,
            limit=settings.OTP_RATE_DEVICE_LIMIT,
            window=settings.OTP_RATE_DEVICE_WINDOW,
        )

    @classmethod
    def check_ip(cls, ip: str) -> RateLimitResult:
        key = f"otp:rate:ip:{ip}"

        return cls._check(
            key=key,
            limit=settings.OTP_RATE_IP_LIMIT,
            window=settings.OTP_RATE_IP_WINDOW,
        )