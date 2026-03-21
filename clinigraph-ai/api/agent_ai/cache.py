import redis

from .config import settings


class RedisCache:
    def __init__(self):
        self.client = None
        self._fallback = {}
        self._redis_available = False

        try:
            self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            self.client.ping()
        except Exception:
            self._redis_available = False
        else:
            self._redis_available = True

    def get(self, key: str):
        if self._redis_available:
            return self.client.get(key)
        return self._fallback.get(key)

    def set(self, key: str, value: str):
        if self._redis_available:
            self.client.setex(key, settings.cache_ttl_seconds, value)
            return
        self._fallback[key] = value
