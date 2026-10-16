import copy
import threading
from pathlib import Path

from app.records.checks import require_record, require_record_type, require_str
from app.records.json_files import read_json_or_set_aside, write_json_atomic


def _validate_file(data):
    if not isinstance(data, dict):
        raise ValueError("snapshot root must be an object")
    for record_type, records in data.items():
        if not isinstance(records, dict):
            raise ValueError(f"snapshot entry for {record_type!r} must be an object")


class SnapshotStore:
    """Local JSON copy of every user record; the last-resort read source.

    An older version never overwrites a newer one.
    Every value is type-checked before it is stored.
    """

    name = "snapshot"

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        data = read_json_or_set_aside(self.path, _validate_file)
        self._data = data if data is not None else {}

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        with self._lock:
            existing = self._data.get(record_type, {}).get(record["id"])
            if existing is not None and existing["version"] > record["version"]:
                return
            self._data.setdefault(record_type, {})[record["id"]] = copy.deepcopy(record)
            write_json_atomic(self.path, self._data)

    def get(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        with self._lock:
            record = self._data.get(record_type, {}).get(record_id)
            return copy.deepcopy(record) if record is not None else None

    def list(self, record_type):
        require_record_type(record_type)
        with self._lock:
            return [copy.deepcopy(record) for record in self._data.get(record_type, {}).values()]

    def delete(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        with self._lock:
            removed = self._data.get(record_type, {}).pop(record_id, None)
            if removed is not None:
                write_json_atomic(self.path, self._data)