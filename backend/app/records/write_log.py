import json
import logging
import uuid

from confluent_kafka import OFFSET_BEGINNING, Consumer, Producer, TopicPartition


log = logging.getLogger(__name__)

TOPIC = "record-writes"
PARTITION = 0
CONFIRM_TIMEOUT_SECONDS = 2
READ_TIMEOUT_SECONDS = 5


def _report_delivery(error, _):
    if error is not None:
        log.error("failed to deliver message with error: %s", error)


class WriteLog:
    def __init__(self, kafka_bootstrap_servers):
        self._bootstrap_servers = kafka_bootstrap_servers
        self._producer = Producer({
            "bootstrap.servers": self._bootstrap_servers,
            "acks": "all",
            "message.timeout.ms": 5000,
        })

    def append(self, op, record_type, record_id, record=None):
        message = {
            "op": op,
            "record_type": record_type,
            "record_id": record_id,
            "record": record,
        }
        try:
            self._producer.produce(
                TOPIC,
                key=f"{record_type}:{record_id}",
                value=json.dumps(message),
                on_delivery=_report_delivery,
            )
            if self._producer.flush(CONFIRM_TIMEOUT_SECONDS) > 0:
                log.warning("failed to confirm delivery of message: %s", message)
        except Exception:
            log.exception("failed to append message: %s", message)

    def read_latest(self):
        consumer = Consumer({
            "bootstrap.servers": self._bootstrap_servers,
            "group.id": f"replay-{uuid.uuid4()}",
            "enable.auto.commit": False,
        })
        try:
            partition = TopicPartition(TOPIC, PARTITION, OFFSET_BEGINNING)
            offsets = consumer.get_watermark_offsets(partition, timeout=READ_TIMEOUT_SECONDS)
            if offsets is None:
                raise RuntimeError("failed to get watermark offsets for topic partition")

            next_offset, end_offset = offsets
            consumer.assign([partition])
            latest = {}
            while next_offset < end_offset:
                message = consumer.poll(timeout=READ_TIMEOUT_SECONDS)
                if message is None:
                    raise RuntimeError("failed to read message from topic partition")
                if message.error():
                    raise RuntimeError(f"error reading message from topic partition: {message.error()}")

                entry = json.loads(message.value())
                latest[(entry["record_type"], entry["record_id"])] = entry
                next_offset = message.offset() + 1

            return latest

        finally:
            consumer.close()
