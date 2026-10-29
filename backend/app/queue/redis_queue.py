import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

UNAVAILABLE_ERRORS = (RedisConnectionError, RedisTimeoutError)
QUEUE_KEY = "app:run_queue"

class RunQueue:

    def __init__(self, redis_client):
        self._client = redis_client

    def push(self, run_ids):
        if not run_ids: return
        try:
            self._client.rpush(QUEUE_KEY, run_ids)
        except UNAVAILABLE_ERRORS:
            pass

    def pop(self):
        try:
            run_id = self._client.lpop(QUEUE_KEY)
            return run_id
        except UNAVAILABLE_ERRORS:
            return None