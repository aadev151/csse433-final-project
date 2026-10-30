import threading
import uuid
from datetime import datetime, timezone

from app.records.checks import require_int, require_record, require_record_type, require_str
from app.records.models import STORE_NAMES, WriteInfo
from app.records.stores import StoreUnavailable

PROTECTED_FIELDS = ("id", "version", "created_at", "updated_at")


class RecordNotFound(Exception):
    def __init__(self, record_type, record_id):
        super().__init__(f"{record_type} {record_id} was not found")
        self.record_type = record_type
        self.record_id = record_id


class RecordExists(Exception):
    def __init__(self, record_type, record_id):
        super().__init__(f"{record_type} {record_id} already exists")
        self.record_type = record_type
        self.record_id = record_id


class VersionConflict(Exception):
    def __init__(self, record_type, record_id, expected_version, current_version):
        super().__init__(
            f"{record_type} {record_id} is at version {current_version}, not {expected_version}"
        )
        self.record_type = record_type
        self.record_id = record_id
        self.expected_version = expected_version
        self.current_version = current_version


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id():
    return str(uuid.uuid4())


class ReplicatedRecords:
    """Keeps every user record in MongoDB, Cassandra, Redis, and the local snapshot.

    Writes always reach the snapshot; stores that are down get a pending write.
    Reads fall back mongodb -> cassandra -> redis -> snapshot, and each store's
    answer is corrected with its pending writes so it is never behind.
    Assumes a single backend process.
    """

    def __init__(self, stores, pending_writes, snapshot, clock=utc_now_iso, id_factory=new_id, write_log=None):
        names = tuple(store.name for store in stores)
        if names != STORE_NAMES:
            raise ValueError(f"stores must be {list(STORE_NAMES)} in that order, got {list(names)}")
        self.stores = list(stores)
        self.pending_writes = pending_writes
        self.snapshot = snapshot
        self.clock = clock
        self.id_factory = id_factory
        self._write_lock = threading.Lock()
        self.write_log = write_log

    # Writes

    def create(self, record_type, fields, record_id=None):
        require_record_type(record_type)
        fields = self._check_fields(fields)
        with self._write_lock:
            if record_id is None:
                record_id = self.id_factory()
            require_str("record_id", record_id)
            if self._latest(record_type, record_id) is not None:
                raise RecordExists(record_type, record_id)
            now = self.clock()
            record = {
                **fields,
                "id": record_id,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            return record, self._write_everywhere(record_type, record)

    def update(self, record_type, record_id, fields, expected_version=None):
        require_record_type(record_type)
        require_str("record_id", record_id)
        fields = self._check_fields(fields)
        if expected_version is not None:
            require_int("expected_version", expected_version, minimum=1)
        with self._write_lock:
            current = self._latest(record_type, record_id)
            if current is None:
                raise RecordNotFound(record_type, record_id)
            if expected_version is not None and expected_version != current["version"]:
                raise VersionConflict(record_type, record_id, expected_version, current["version"])
            record = {
                **current,
                **fields,
                "id": record_id,
                "version": current["version"] + 1,
                "updated_at": self.clock(),
            }
            return record, self._write_everywhere(record_type, record)

    def delete(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        with self._write_lock:
            if self._latest(record_type, record_id) is None:
                raise RecordNotFound(record_type, record_id)
            self._log_write("delete", record_type, record_id)
            self.snapshot.delete(record_type, record_id)
            written = []
            pending = []
            for store in self.stores:
                try:
                    store.delete(record_type, record_id)
                    written.append(store.name)
                except StoreUnavailable:
                    self.pending_writes.add(store.name, record_type, record_id, "delete")
                    pending.append(store.name)
            return WriteInfo.from_results(written, pending)

    # Reads

    def get(self, record_type, record_id):
        """Return (record or None, served_by)."""
        require_record_type(record_type)
        require_str("record_id", record_id)
        pending = self._pending_for(record_type)
        for store in self.stores:
            try:
                record = store.get(record_type, record_id)
            except StoreUnavailable:
                continue
            return self._apply_pending(record, pending.get((store.name, record_id))), store.name
        return self.snapshot.get(record_type, record_id), "snapshot"

    def list(self, record_type):
        """Return (records, served_by)."""
        require_record_type(record_type)
        pending = self._pending_for(record_type)
        for store in self.stores:
            try:
                records = store.list(record_type)
            except StoreUnavailable:
                continue
            by_id = {record["id"]: record for record in records}
            for (store_name, record_id), entry in pending.items():
                if store_name != store.name:
                    continue
                corrected = self._apply_pending(by_id.get(record_id), entry)
                if corrected is None:
                    by_id.pop(record_id, None)
                else:
                    by_id[record_id] = corrected
            return list(by_id.values()), store.name
        return self.snapshot.list(record_type), "snapshot"

    # Background sync

    def sync(self):
        """Apply pending writes to stores that are back up. Returns how many were applied."""
        applied = 0
        still_down = set()
        with self._write_lock:
            for entry in self.pending_writes.pending():
                if entry.store in still_down:
                    continue
                store = self._store_named(entry.store)
                try:
                    if entry.op == "put":
                        current = store.get(entry.record_type, entry.record_id)
                        if current is None or current["version"] < entry.record["version"]:
                            store.put(entry.record_type, entry.record)
                    else:
                        store.delete(entry.record_type, entry.record_id)
                except StoreUnavailable as error:
                    self.pending_writes.mark_failed(entry.seq, str(error))
                    still_down.add(entry.store)
                    continue
                self.pending_writes.remove(entry.seq)
                applied += 1
        return applied

    def pending_counts(self):
        return self.pending_writes.counts()

    def _log_write(self, op, record_type, record_id, record=None):
        if self.write_log is not None:
            self.write_log.append(op, record_type, record_id, record)

    def replay_from_log(self, store_name):
        if self.write_log is None:
            raise RuntimeError("no write log configured")

        store = self._store_named(store_name)
        latest = self.write_log.read_latest()
        restored = deleted = already_current = 0
        with self._write_lock:
            for (record_type, record_id), entry in latest.items():
                existing = store.get(record_type, record_id)
                if entry["op"] == "delete":
                    if existing is not None:
                        store.delete(record_type, record_id)
                        deleted += 1
                    continue
                if existing is None or existing["version"] < entry["record"]["version"]:
                    store.put(record_type, entry["record"])
                    restored += 1
                else:
                    already_current += 1

        return {
            "store": store_name,
            "records_in_log": len(latest),
            "restored": restored,
            "deleted": deleted,
            "already_current": already_current,
        }

    # Helpers

    def _write_everywhere(self, record_type, record):
        require_record(record)
        self._log_write("put", record_type, record["id"], record)
        self.snapshot.put(record_type, record)
        written = []
        pending = []
        for store in self.stores:
            try:
                store.put(record_type, record)
                written.append(store.name)
            except StoreUnavailable:
                self.pending_writes.add(store.name, record_type, record["id"], "put", record)
                pending.append(store.name)
        return WriteInfo.from_results(written, pending)

    def _latest(self, record_type, record_id):
        candidates = []
        record, _ = self.get(record_type, record_id)
        if record is not None:
            candidates.append(record)
        snapshot_record = self.snapshot.get(record_type, record_id)
        if snapshot_record is not None:
            candidates.append(snapshot_record)
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate["version"])

    def _pending_for(self, record_type):
        return {
            (entry.store, entry.record_id): entry
            for entry in self.pending_writes.pending()
            if entry.record_type == record_type
        }

    def _apply_pending(self, record, entry):
        if entry is None:
            return record
        if entry.op == "delete":
            return None
        if record is None or record["version"] < entry.record["version"]:
            return entry.record
        return record

    def _store_named(self, name):
        for store in self.stores:
            if store.name == name:
                return store
        raise ValueError(f"no store named {name}")

    def _check_fields(self, fields):
        if not isinstance(fields, dict):
            raise TypeError(f"fields must be a dict, got {type(fields).__name__}")
        protected = [key for key in PROTECTED_FIELDS if key in fields]
        if protected:
            raise ValueError(f"fields cannot set {protected}; they are managed automatically")
        return dict(fields)