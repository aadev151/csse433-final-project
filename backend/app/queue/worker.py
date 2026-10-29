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