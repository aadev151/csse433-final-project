import copy
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.records.checks import (
    require_choice,
    require_int,
    require_record,
    require_record_type,
    require_store,
    require_str,
)
from app.records.json_files import read_json_or_set_aside, write_json_atomic
from app.records.models import STORE_NAMES

OPS = ("put", "delete")
ENTRY_KEYS = {
    "seq",
    "store",
    "record_type",
    "record_id",
    "op",
    "record",
    "attempts",
    "last_error",
    "created_at",
}


@dataclass
class PendingWrite:
    seq: int
    store: str
    record_type: str
    record_id: str
    op: str
    record: Optional[dict]
    attempts: int
    last_error: Optional[str]
    created_at: float


def _validate_file(data):
    if not isinstance(data, dict):
        raise ValueError("pending writes file root must be an object")
    require_int("next_seq", data.get("next_seq"), minimum=1)
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    for entry in entries:
        if not isinstance(entry, dict) or not ENTRY_KEYS <= entry.keys():
            raise ValueError("every entry must be an object with all entry fields")
        require_int("seq", entry["seq"], minimum=1)
        require_store(entry["store"])
        require_record_type(entry["record_type"])
        require_str("record_id", entry["record_id"])
        require_choice("op", entry["op"], OPS)


class PendingWrites:
    """Durable queue of writes that still need to reach a store, kept in a local JSON file.

    Keeps only the latest operation per (store, record_type, record_id).
    Sequence numbers are never reused, so remove(seq) never deletes a newer entry.
    Every value is type-checked before it is stored.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        data = read_json_or_set_aside(self.path, _validate_file)
        if data is None:
            data = {"next_seq": 1, "entries": []}
        highest_seq = max((entry["seq"] for entry in data["entries"]), default=0)
        data["next_seq"] = max(data["next_seq"], highest_seq + 1)
        self._data = data

    def add(self, store, record_type, record_id, op, record=None):
        require_store(store)
        require_record_type(record_type)
        require_str("record_id", record_id)
        require_choice("op", op, OPS)
        if op == "put":
            if record is None:
                raise ValueError("put requires a record")
            require_record(record, record_id=record_id)
        elif record is not None:
            raise ValueError("delete must not include a record")

        with self._lock:
            key = (store, record_type, record_id)
            entries = [
                entry
                for entry in self._data["entries"]
                if (entry["store"], entry["record_type"], entry["record_id"]) != key
            ]
            seq = self._data["next_seq"]
            entries.append(
                {
                    "seq": seq,
                    "store": store,
                    "record_type": record_type,
                    "record_id": record_id,
                    "op": op,
                    "record": copy.deepcopy(record) if op == "put" else None,
                    "attempts": 0,
                    "last_error": None,
                    "created_at": time.time(),
                }
            )
            self._commit({"next_seq": seq + 1, "entries": entries})
            return seq

    def pending(self, store=None, limit=None):
        if store is not None:
            require_store(store)
        if limit is not None:
            require_int("limit", limit, minimum=1)
        with self._lock:
            entries = sorted(self._data["entries"], key=lambda entry: entry["seq"])
            if store is not None:
                entries = [entry for entry in entries if entry["store"] == store]
            if limit is not None:
                entries = entries[:limit]
            return [self._to_entry(entry) for entry in entries]

    def remove(self, seq):
        require_int("seq", seq, minimum=1)
        with self._lock:
            entries = [entry for entry in self._data["entries"] if entry["seq"] != seq]
            if len(entries) != len(self._data["entries"]):
                self._commit({"next_seq": self._data["next_seq"], "entries": entries})

    def mark_failed(self, seq, error):
        require_int("seq", seq, minimum=1)
        require_str("error", error)
        with self._lock:
            entries = []
            found = False
            for entry in self._data["entries"]:
                if entry["seq"] == seq:
                    entry = {**entry, "attempts": entry["attempts"] + 1, "last_error": error}
                    found = True
                entries.append(entry)
            if found:
                self._commit({"next_seq": self._data["next_seq"], "entries": entries})

    def counts(self):
        with self._lock:
            result = {name: 0 for name in STORE_NAMES}
            for entry in self._data["entries"]:
                result[entry["store"]] += 1
            return result

    def close(self):
        """Nothing to release; every change is already on disk."""

    def _commit(self, new_data):
        write_json_atomic(self.path, new_data)
        self._data = new_data

    def _to_entry(self, entry):
        return PendingWrite(
            seq=entry["seq"],
            store=entry["store"],
            record_type=entry["record_type"],
            record_id=entry["record_id"],
            op=entry["op"],
            record=copy.deepcopy(entry["record"]),
            attempts=entry["attempts"],
            last_error=entry["last_error"],
            created_at=entry["created_at"],
        )