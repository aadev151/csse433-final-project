import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

UNAVAILABLE_ERRORS = (RedisConnectionError, RedisTimeoutError)
QUEUE_KEY = "app:run_queue"

class RunQueue:

    def __init__(self, redis_client):
        self.client = redis_client

    def push(self, run_ids):
        if not run_ids: return
        try:
            self.client.rpush(QUEUE_KEY, run_ids)
        except UNAVAILABLE_ERRORS:
            pass