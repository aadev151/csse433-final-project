import copy

from app.records.checks import require_record, require_record_type, require_str
from app.records.models import STORE_NAMES


class StoreUnavailable(Exception):
    def __init__(self, store_name, message=None):
        super().__init__(message or f"{store_name} is unavailable")
        self.store_name = store_name


class RecordStore:
    """Interface every store adapter implements.

    Records are plain dicts that always contain "id" and "version".
    get returns None when the record does not exist in this store.
    Every method raises StoreUnavailable when the store cannot be reached.
    """

    name = "base"

    def put(self, record_type, record):
        raise NotImplementedError

    def get(self, record_type, record_id):
        raise NotImplementedError

    def list(self, record_type):
        raise NotImplementedError

    def delete(self, record_type, record_id):
        raise NotImplementedError

    def ping(self):
        raise NotImplementedError


class InMemoryStore(RecordStore):
    """Fake store for tests. Can be switched down to simulate an outage."""

    def __init__(self, name):
        if name not in STORE_NAMES:
            raise ValueError(f"unknown store name: {name}")
        self.name = name
        self._records = {}
        self._up = True

    def set_down(self):
        self._up = False

    def set_up(self):
        self._up = True

    def _check_up(self):
        if not self._up:
            raise StoreUnavailable(self.name)

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        self._check_up()
        self._records.setdefault(record_type, {})[record["id"]] = copy.deepcopy(record)

    def get(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        self._check_up()
        record = self._records.get(record_type, {}).get(record_id)
        return copy.deepcopy(record) if record is not None else None

    def list(self, record_type):
        require_record_type(record_type)
        self._check_up()
        return [copy.deepcopy(record) for record in self._records.get(record_type, {}).values()]

    def delete(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        self._check_up()
        self._records.get(record_type, {}).pop(record_id, None)

    def ping(self):
        self._check_up()
        return 0.0