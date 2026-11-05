import json
import logging
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

UNAVAILABLE_ERRORS = (RedisConnectionError, RedisTimeoutError)
log = logging.getLogger(__name__)


class RunBroadcast:
     
    def __init__(self, redis_client):
        self._client = redis_client

    def _channel(self, run_id):
        channel_name = f"run:{run_id}"
        return channel_name

    def _publish(self, run_id, message):
        channel = self._channel(run_id)
        payload = json.dumps(message)
        try:
            self._client.publish(channel, payload)
        except UNAVAILABLE_ERRORS:
            log.debug("redis pub/sub unavailable, skipping publish for run %s", run_id)

    def send_status(self, run_id, status):
        message = {
            "type":"status:",
            "status": status
        }
        return self._publish(run_id, message)