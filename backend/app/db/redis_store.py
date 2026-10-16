import json
import re
import time

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ReadOnlyError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.sentinel import Sentinel

from app.records.checks import require_record, require_record_type, require_str
from app.records.stores import RecordStore, StoreUnavailable

KEY_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
UNAVAILABLE_ERRORS = (RedisConnectionError, RedisTimeoutError, ReadOnlyError)


class RedisStore(RecordStore):
    """User records in Redis.

    Each record is a hash at <prefix>:<type>:<id> with fields "version" and "body" (JSON).
    A set at <prefix>:index:<type> lists the ids of each record type.
    """

    name = "redis"

    def __init__(self, client, key_prefix="app"):
        require_str("key_prefix", key_prefix)
        if not KEY_PREFIX_PATTERN.match(key_prefix):
            raise ValueError(f"invalid Redis key prefix: {key_prefix!r}")
        self._client = client
        self._prefix = key_prefix

    @classmethod
    def from_url(cls, url, key_prefix="app", timeout_seconds=2.0):
        require_str("url", url)
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=timeout_seconds,
            socket_connect_timeout=timeout_seconds,
        )
        return cls(client, key_prefix=key_prefix)

    @classmethod
    def from_sentinels(cls, sentinels, master_name, password=None, key_prefix="app", timeout_seconds=2.0):
        if not sentinels:
            raise ValueError("at least one Sentinel address is required")
        require_str("master_name", master_name)
        sentinel = Sentinel(
            list(sentinels),
            socket_timeout=timeout_seconds,
            sentinel_kwargs={"socket_timeout": timeout_seconds},
        )
        client = sentinel.master_for(
            master_name,
            password=password,
            decode_responses=True,
            socket_timeout=timeout_seconds,
            socket_connect_timeout=timeout_seconds,
        )
        return cls(client, key_prefix=key_prefix)

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        body = json.dumps(record, allow_nan=False)
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.hset(
                self._record_key(record_type, record["id"]),
                mapping={"version": str(record["version"]), "body": body},
            )
            pipe.sadd(self._index_key(record_type), record["id"])
            pipe.execute()
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def get(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        try:
            body = self._client.hget(self._record_key(record_type, record_id), "body")
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error
        return json.loads(body) if body is not None else None

    def list(self, record_type):
        require_record_type(record_type)
        try:
            ids = sorted(self._client.smembers(self._index_key(record_type)))
            if not ids:
                return []
            pipe = self._client.pipeline(transaction=False)
            for record_id in ids:
                pipe.hget(self._record_key(record_type, record_id), "body")
            bodies = pipe.execute()
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error
        return [json.loads(body) for body in bodies if body is not None]

    def delete(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.delete(self._record_key(record_type, record_id))
            pipe.srem(self._index_key(record_type), record_id)
            pipe.execute()
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def ping(self):
        started = time.perf_counter()
        try:
            self._client.ping()
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error
        return (time.perf_counter() - started) * 1000

    def close(self):
        self._client.close()

    def _record_key(self, record_type, record_id):
        return f"{self._prefix}:{record_type}:{record_id}"

    def _index_key(self, record_type):
        return f"{self._prefix}:index:{record_type}"