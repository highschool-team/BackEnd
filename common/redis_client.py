import redis as redis_lib
from django.conf import settings

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = redis_lib.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
        )
    return _pool


def get_redis():
    return redis_lib.Redis(connection_pool=_get_pool())
