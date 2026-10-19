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

    def _record_key(self, record_type, record_id):
        key = f'app:{record_type}:{record_id}'
        return key

    def _index_key(self, record_type):
        key = f'app:index:{record_type}'
        return key

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        record_id = record["id"]
        version = record["version"]
        body = json.dumps(record, allow_nan = False)
        record_key = self._record_key(record_type, record_id)
        index_key = self._index_key(record_type)
        hash_fields = {"version": str(version), "body": body}
        try:
            pipe = self._client.pipeline(transaction = True)
            pipe.hset(record_key, mapping = hash_fields)
            pipe.sadd(index_key, record_id)
            pipe.execute()
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def get(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        record_key = self._record_key(record_type, record_id)
        try:
            body = self._client.hget(record_key, "body")
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error
        if body is None:
            return None
        record = json.loads(body)
        return record
