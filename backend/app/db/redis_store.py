import json
import time
import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ReadOnlyError
from redis.exceptions import TimeoutError as RedisTimeoutError
from app.records.checks import require_record, require_record_type, require_str
from app.records.stores import RecordStore, StoreUnavailable

UNAVAILABLE_ERRORS = (RedisConnectionError, RedisTimeoutError, ReadOnlyError)


class RedisStore(RecordStore):

    name = "redis"

    def __init__(self, url, timeout_seconds=2.0):
        require_str("url", url)
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=timeout_seconds,
            socket_connect_timeout=timeout_seconds,
        )
        self._client = client