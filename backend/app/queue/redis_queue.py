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
            self._client.rpush(QUEUE_KEY, *run_ids)
        except UNAVAILABLE_ERRORS:
            pass

    def pop(self):
        try:
            run_id = self._client.lpop(QUEUE_KEY)
            return run_id
        except UNAVAILABLE_ERRORS:
            return None
        
    def peek(self):
        try:
            all_ids = self._client.lrange(QUEUE_KEY, 0, -1)
            return all_ids
        except UNAVAILABLE_ERRORS:
            return []

    def remove(self, run_id):
        try:
            self._client.lrem(QUEUE_KEY, 0, run_id)
        except UNAVAILABLE_ERRORS:
            pass

    def length(self):
        try:
            count = self._client.llen(QUEUE_KEY)
            return count
        except UNAVAILABLE_ERRORS:
            return 0
        