from types import SimpleNamespace

import pytest

from app.records.models import STORE_NAMES
from app.records.pending_writes import PendingWrites
from app.records.replicated import (
    RecordExists,
    RecordNotFound,
    ReplicatedRecords,
    VersionConflict,
)
from app.records.snapshot import SnapshotStore
from app.records.stores import InMemoryStore

T0 = "2026-10-16T12:00:00.000Z"
T1 = "2026-10-16T12:00:01.000Z"
T2 = "2026-10-16T12:00:02.000Z"


@pytest.fixture
def env(tmp_path):
    stores = {name: InMemoryStore(name) for name in STORE_NAMES}
    pending = PendingWrites(tmp_path / "pending_writes.json")
    snapshot = SnapshotStore(tmp_path / "snapshot.json")
    times = iter(f"2026-10-16T12:00:{n:02d}.000Z" for n in range(60))
    ids = iter(f"id-{n}" for n in range(1, 100))
    records = ReplicatedRecords(
        [stores[name] for name in STORE_NAMES],
        pending,
        snapshot,
        clock=lambda: next(times),
        id_factory=lambda: next(ids),
    )
    return SimpleNamespace(records=records, stores=stores, pending=pending, snapshot=snapshot)


# Create

def test_create_with_all_stores_up(env):
    record, write = env.records.create("signal", {"name": "btc_volume"})
    assert record == {
        "name": "btc_volume",
        "id": "id-1",
        "version": 1,
        "created_at": T0,
        "updated_at": T0,
    }
    assert write.status == "committed"
    assert write.stores_written == ["mongodb", "cassandra", "redis"]
    for store in env.stores.values():
        assert store.get("signal", "id-1") == record
    assert env.snapshot.get("signal", "id-1") == record


def test_create_with_fixed_id(env):
    record, _ = env.records.create("signal", {"name": "last price"}, record_id="builtin-last-price")
    assert record["id"] == "builtin-last-price"


def test_create_with_existing_id_raises(env):
    env.records.create("signal", {"name": "a"}, record_id="builtin-x")
    with pytest.raises(RecordExists):
        env.records.create("signal", {"name": "b"}, record_id="builtin-x")


def test_create_with_store_down_is_pending(env):
    env.stores["cassandra"].set_down()
    record, write = env.records.create("signal", {"name": "btc_volume"})
    assert write.status == "pending"
    assert write.stores_written == ["mongodb", "redis"]
    assert write.stores_pending == ["cassandra"]
    assert env.pending.counts() == {"mongodb": 0, "cassandra": 1, "redis": 0}
    assert env.stores["mongodb"].get("signal", record["id"]) == record


def test_create_with_all_stores_down_is_still_readable(env):
    for store in env.stores.values():
        store.set_down()
    record, write = env.records.create("signal", {"name": "btc_volume"})
    assert write.status == "pending"
    assert write.stores_written == []
    assert env.records.get("signal", record["id"]) == (record, "snapshot")


@pytest.mark.parametrize("field", ["id", "version", "created_at", "updated_at"])
def test_create_rejects_managed_fields(env, field):
    with pytest.raises(ValueError):
        env.records.create("signal", {"name": "x", field: "nope"})


def test_create_rejects_non_dict_fields(env):
    with pytest.raises(TypeError):
        env.records.create("signal", ["name", "x"])


def test_create_rejects_unknown_record_type(env):
    with pytest.raises(ValueError):
        env.records.create("users", {"name": "x"})


# Get

def test_get_from_mongodb_when_up(env):
    record, _ = env.records.create("signal", {"name": "x"})
    assert env.records.get("signal", record["id"]) == (record, "mongodb")


def test_get_falls_back_to_cassandra(env):
    record, _ = env.records.create("signal", {"name": "x"})
    env.stores["mongodb"].set_down()
    assert env.records.get("signal", record["id"]) == (record, "cassandra")


def test_get_falls_back_to_redis(env):
    record, _ = env.records.create("signal", {"name": "x"})
    env.stores["mongodb"].set_down()
    env.stores["cassandra"].set_down()
    assert env.records.get("signal", record["id"]) == (record, "redis")


def test_get_missing_returns_none(env):
    assert env.records.get("signal", "nope") == (None, "mongodb")


def test_get_corrects_store_with_pending_write(env):
    env.stores["cassandra"].set_down()
    record, _ = env.records.create("signal", {"name": "x"})
    env.stores["mongodb"].set_down()
    env.stores["cassandra"].set_up()
    assert env.records.get("signal", record["id"]) == (record, "cassandra")


# Update

def test_update_bumps_version_and_keeps_created_at(env):
    record, _ = env.records.create("signal", {"name": "old", "window_ms": 1000})
    updated, write = env.records.update("signal", record["id"], {"name": "new"})
    assert updated == {
        "name": "new",
        "window_ms": 1000,
        "id": record["id"],
        "version": 2,
        "created_at": T0,
        "updated_at": T1,
    }
    assert write.status == "committed"
    assert env.stores["redis"].get("signal", record["id"]) == updated


def test_update_with_matching_expected_version(env):
    record, _ = env.records.create("signal", {"name": "old"})
    updated, _ = env.records.update("signal", record["id"], {"name": "new"}, expected_version=1)
    assert updated["version"] == 2


def test_update_with_wrong_expected_version_raises(env):
    record, _ = env.records.create("signal", {"name": "old"})
    env.records.update("signal", record["id"], {"name": "newer"})
    with pytest.raises(VersionConflict) as error:
        env.records.update("signal", record["id"], {"name": "stale edit"}, expected_version=1)
    assert error.value.current_version == 2


def test_update_missing_raises(env):
    with pytest.raises(RecordNotFound):
        env.records.update("signal", "nope", {"name": "x"})


def test_update_rejects_managed_fields(env):
    record, _ = env.records.create("signal", {"name": "x"})
    with pytest.raises(ValueError):
        env.records.update("signal", record["id"], {"version": 99})


def test_update_never_reuses_a_version(env):
    record, _ = env.records.create("signal", {"name": "v1"})
    env.stores["cassandra"].set_down()
    env.records.update("signal", record["id"], {"name": "v2"})
    env.stores["mongodb"].set_down()
    env.stores["cassandra"].set_up()
    updated, _ = env.records.update("signal", record["id"], {"name": "v3"})
    assert updated["version"] == 3


# Delete

def test_delete_removes_everywhere(env):
    record, _ = env.records.create("signal", {"name": "x"})
    write = env.records.delete("signal", record["id"])
    assert write.status == "committed"
    for store in env.stores.values():
        assert store.get("signal", record["id"]) is None
    assert env.snapshot.get("signal", record["id"]) is None


def test_delete_missing_raises(env):
    with pytest.raises(RecordNotFound):
        env.records.delete("signal", "nope")


def test_delete_with_store_down_hides_record_on_read(env):
    record, _ = env.records.create("signal", {"name": "x"})
    env.stores["redis"].set_down()
    write = env.records.delete("signal", record["id"])
    assert write.stores_pending == ["redis"]
    env.stores["mongodb"].set_down()
    env.stores["cassandra"].set_down()
    env.stores["redis"].set_up()
    assert env.records.get("signal", record["id"]) == (None, "redis")


# List

def test_list_from_mongodb(env):
    env.records.create("signal", {"name": "a"})
    env.records.create("signal", {"name": "b"})
    env.records.create("experiment", {"name": "e"})
    records, served_by = env.records.list("signal")
    assert served_by == "mongodb"
    assert sorted(record["name"] for record in records) == ["a", "b"]


def test_list_falls_back_to_snapshot_when_all_down(env):
    env.records.create("signal", {"name": "a"})
    for store in env.stores.values():
        store.set_down()
    records, served_by = env.records.list("signal")
    assert served_by == "snapshot"
    assert [record["name"] for record in records] == ["a"]


def test_list_corrects_store_with_pending_writes(env):
    kept, _ = env.records.create("signal", {"name": "kept"})
    removed, _ = env.records.create("signal", {"name": "removed"})
    env.stores["cassandra"].set_down()
    env.records.create("signal", {"name": "added"})
    env.records.update("signal", kept["id"], {"name": "kept v2"})
    env.records.delete("signal", removed["id"])
    env.stores["mongodb"].set_down()
    env.stores["cassandra"].set_up()
    records, served_by = env.records.list("signal")
    assert served_by == "cassandra"
    assert sorted(record["name"] for record in records) == ["added", "kept v2"]


# Sync

def test_sync_applies_pending_put_after_recovery(env):
    env.stores["cassandra"].set_down()
    record, _ = env.records.create("signal", {"name": "x"})
    env.stores["cassandra"].set_up()
    assert env.records.sync() == 1
    assert env.stores["cassandra"].get("signal", record["id"]) == record
    assert env.pending.pending() == []


def test_sync_applies_pending_delete(env):
    record, _ = env.records.create("signal", {"name": "x"})
    env.stores["redis"].set_down()
    env.records.delete("signal", record["id"])
    env.stores["redis"].set_up()
    env.records.sync()
    assert env.stores["redis"].get("signal", record["id"]) is None
    assert env.pending.pending() == []


def test_sync_keeps_entries_while_store_is_down(env):
    env.stores["cassandra"].set_down()
    env.records.create("signal", {"name": "a"})
    env.records.create("signal", {"name": "b"})
    assert env.records.sync() == 0
    entries = env.pending.pending()
    assert len(entries) == 2
    assert entries[0].attempts == 1
    assert entries[1].attempts == 0


def test_sync_never_overwrites_newer_version(env):
    env.stores["cassandra"].set_down()
    record, _ = env.records.create("signal", {"name": "v1"})
    env.stores["cassandra"].set_up()
    updated, _ = env.records.update("signal", record["id"], {"name": "v2"})
    env.records.sync()
    assert env.stores["cassandra"].get("signal", record["id"]) == updated
    assert env.pending.pending() == []


def test_pending_counts(env):
    env.stores["redis"].set_down()
    env.records.create("signal", {"name": "x"})
    assert env.records.pending_counts() == {"mongodb": 0, "cassandra": 0, "redis": 1}


# Setup checks

def test_rejects_stores_in_wrong_order(tmp_path):
    stores = [InMemoryStore("cassandra"), InMemoryStore("mongodb"), InMemoryStore("redis")]
    with pytest.raises(ValueError):
        ReplicatedRecords(
            stores,
            PendingWrites(tmp_path / "pending_writes.json"),
            SnapshotStore(tmp_path / "snapshot.json"),
        )