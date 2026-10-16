import json
import sqlite3
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
from app.records.models import STORE_NAMES

OPS = ("put", "delete")


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


class PendingWrites:
    """Durable queue of writes that still need to reach a store.

    Keeps only the latest operation per (store, record_type, record_id).
    Every add gets a new seq, so remove(seq) never deletes a newer entry.
    Every value is type-checked before it reaches a query.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_writes (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    store TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    op TEXT NOT NULL,
                    payload TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    UNIQUE (store, record_type, record_id)
                )
                """
            )

    def add(self, store, record_type, record_id, op, record=None):
        require_store(store)
        require_record_type(record_type)
        require_str("record_id", record_id)
        require_choice("op", op, OPS)
        if op == "put":
            if record is None:
                raise ValueError("put requires a record")
            require_record(record, record_id=record_id)
            payload = json.dumps(record, allow_nan=False)
        else:
            if record is not None:
                raise ValueError("delete must not include a record")
            payload = None
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                INSERT OR REPLACE INTO pending_writes
                    (store, record_type, record_id, op, payload, attempts, last_error, created_at)
                VALUES (?, ?, ?, ?, ?, 0, NULL, ?)
                """,
                (store, record_type, record_id, op, payload, time.time()),
            )
            return cursor.lastrowid

    def pending(self, store=None, limit=None):
        query = "SELECT * FROM pending_writes"
        params = []
        if store is not None:
            require_store(store)
            query += " WHERE store = ?"
            params.append(store)
        query += " ORDER BY seq"
        if limit is not None:
            require_int("limit", limit, minimum=1)
            query += " LIMIT ?"
            params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._to_entry(row) for row in rows]

    def remove(self, seq):
        require_int("seq", seq, minimum=1)
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM pending_writes WHERE seq = ?", (seq,))

    def mark_failed(self, seq, error):
        require_int("seq", seq, minimum=1)
        require_str("error", error)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE pending_writes SET attempts = attempts + 1, last_error = ? WHERE seq = ?",
                (error, seq),
            )

    def counts(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT store, COUNT(*) AS n FROM pending_writes GROUP BY store"
            ).fetchall()
        result = {name: 0 for name in STORE_NAMES}
        for row in rows:
            result[row["store"]] = row["n"]
        return result

    def close(self):
        with self._lock:
            self._conn.close()

    def _to_entry(self, row):
        return PendingWrite(
            seq=row["seq"],
            store=row["store"],
            record_type=row["record_type"],
            record_id=row["record_id"],
            op=row["op"],
            record=json.loads(row["payload"]) if row["payload"] is not None else None,
            attempts=row["attempts"],
            last_error=row["last_error"],
            created_at=row["created_at"],
        )