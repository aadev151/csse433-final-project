import copy
import json
import logging
import os
import threading
import time
from pathlib import Path

from app.records.checks import require_record, require_record_type, require_str

log = logging.getLogger(__name__)


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
        self._data = self._load()

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        with self._lock:
            existing = self._data.get(record_type, {}).get(record["id"])
            if existing is not None and existing["version"] > record["version"]:
                return
            self._data.setdefault(record_type, {})[record["id"]] = copy.deepcopy(record)
            self._save()

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
                self._save()

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError("snapshot root must be an object")
            for record_type, records in data.items():
                if not isinstance(records, dict):
                    raise ValueError(f"snapshot entry for {record_type!r} must be an object")
            return data
        except (json.JSONDecodeError, ValueError) as error:
            corrupt_path = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
            self.path.replace(corrupt_path)
            log.warning("snapshot was unreadable (%s); moved to %s", error, corrupt_path)
            return {}

    def _save(self):
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        with open(tmp_path, "w") as file:
            json.dump(self._data, file, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, self.path)