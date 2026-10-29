import logging

from app.records.replicated import RecordNotFound

log = logging.getLogger(__name__)

class RunWorker:

    def __init__(self, records, queue, cassandra_store):
        self._records = records
        self._queue = queue
        self._cassandra = cassandra_store

    def _is_cassandra_up(self):
        try:
            self._cassandra.ping()
            return True
        except Exception:
            return False

    def _update_run(self, run_id, fields):
        try:
            record, _ = self._records.update("run", run_id, fields)
            return record
        except RecordNotFound:
            log.warning("run %s was deleted while being processed", run_id)
            return None