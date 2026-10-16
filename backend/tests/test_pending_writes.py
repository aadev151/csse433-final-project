import json

import pytest

from app.records.pending_writes import PendingWrites


@pytest.fixture
def pending_writes(tmp_path):
    queue = PendingWrites(tmp_path / "pending_writes.json")
    yield queue
    queue.close()


def test_add_then_pending_returns_entry(pending_writes):
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    entries = pending_writes.pending()
    assert len(entries) == 1
    entry = entries[0]
    assert (entry.store, entry.record_type, entry.record_id, entry.op) == ("cassandra", "signal", "s1", "put")
    assert entry.record == {"id": "s1", "version": 1}
    assert entry.attempts == 0


def test_latest_op_replaces_earlier_for_same_record(pending_writes):
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 2})
    entries = pending_writes.pending()
    assert len(entries) == 1
    assert entries[0].record["version"] == 2


def test_delete_replaces_pending_put(pending_writes):
    pending_writes.add("redis", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.add("redis", "signal", "s1", "delete")
    entries = pending_writes.pending()
    assert len(entries) == 1
    assert entries[0].op == "delete"
    assert entries[0].record is None


def test_same_record_pending_for_different_stores(pending_writes):
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.add("redis", "signal", "s1", "put", {"id": "s1", "version": 1})
    assert len(pending_writes.pending()) == 2
    assert len(pending_writes.pending(store="redis")) == 1


def test_remove_by_seq(pending_writes):
    seq = pending_writes.add("mongodb", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.remove(seq)
    assert pending_writes.pending() == []


def test_removing_stale_seq_keeps_newer_entry(pending_writes):
    old_seq = pending_writes.add("mongodb", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.add("mongodb", "signal", "s1", "put", {"id": "s1", "version": 2})
    pending_writes.remove(old_seq)
    entries = pending_writes.pending()
    assert len(entries) == 1
    assert entries[0].record["version"] == 2


def test_mark_failed_records_attempt_and_error(pending_writes):
    seq = pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.mark_failed(seq, "connection refused")
    pending_writes.mark_failed(seq, "still down")
    entry = pending_writes.pending()[0]
    assert entry.attempts == 2
    assert entry.last_error == "still down"


def test_counts_per_store(pending_writes):
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.add("cassandra", "signal", "s2", "put", {"id": "s2", "version": 1})
    pending_writes.add("redis", "experiment", "e1", "delete")
    assert pending_writes.counts() == {"mongodb": 0, "cassandra": 2, "redis": 1}


def test_pending_is_in_insertion_order(pending_writes):
    pending_writes.add("cassandra", "signal", "s2", "put", {"id": "s2", "version": 1})
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    assert [entry.record_id for entry in pending_writes.pending()] == ["s2", "s1"]


def test_pending_limit(pending_writes):
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    pending_writes.add("cassandra", "signal", "s2", "put", {"id": "s2", "version": 1})
    assert len(pending_writes.pending(limit=1)) == 1


def test_returned_record_is_a_copy(pending_writes):
    pending_writes.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1, "params": {"field": "qty"}})
    entry = pending_writes.pending()[0]
    entry.record["params"]["field"] = "changed"
    assert pending_writes.pending()[0].record["params"]["field"] == "qty"


# Durability

def test_survives_reopen(tmp_path):
    path = tmp_path / "pending_writes.json"
    first = PendingWrites(path)
    first.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    first.close()
    second = PendingWrites(path)
    assert len(second.pending()) == 1
    second.close()


def test_seq_is_never_reused_after_reopen(tmp_path):
    path = tmp_path / "pending_writes.json"
    first = PendingWrites(path)
    old_seq = first.add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    first.remove(old_seq)
    second = PendingWrites(path)
    new_seq = second.add("cassandra", "signal", "s2", "put", {"id": "s2", "version": 1})
    assert new_seq > old_seq


def test_file_is_valid_json_with_no_leftover_temp_file(tmp_path):
    path = tmp_path / "pending_writes.json"
    PendingWrites(path).add("cassandra", "signal", "s1", "put", {"id": "s1", "version": 1})
    data = json.loads(path.read_text())
    assert data["entries"][0]["record_id"] == "s1"
    assert [p.name for p in tmp_path.iterdir()] == ["pending_writes.json"]


def test_corrupt_file_is_set_aside(tmp_path):
    path = tmp_path / "pending_writes.json"
    path.write_text("not json {")
    queue = PendingWrites(path)
    assert queue.pending() == []
    assert any(p.name.startswith("pending_writes.json.corrupt-") for p in tmp_path.iterdir())


def test_wrong_shape_file_is_set_aside(tmp_path):
    path = tmp_path / "pending_writes.json"
    path.write_text(json.dumps({"next_seq": 1, "entries": [{"seq": "one"}]}))
    queue = PendingWrites(path)
    assert queue.pending() == []
    assert any(p.name.startswith("pending_writes.json.corrupt-") for p in tmp_path.iterdir())


# Parameter checks

def test_rejects_unknown_store(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.add("postgres", "signal", "s1", "put", {"id": "s1", "version": 1})


def test_rejects_unknown_record_type(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.add("redis", "users", "s1", "put", {"id": "s1", "version": 1})


def test_rejects_unknown_op(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.add("redis", "signal", "s1", "upsert", {"id": "s1", "version": 1})


def test_rejects_non_string_record_id(pending_writes):
    with pytest.raises(TypeError):
        pending_writes.add("redis", "signal", 1, "delete")


def test_put_requires_record(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.add("redis", "signal", "s1", "put")


def test_put_rejects_non_dict_record(pending_writes):
    with pytest.raises(TypeError):
        pending_writes.add("redis", "signal", "s1", "put", ["s1", 1])


def test_put_rejects_record_with_different_id(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.add("redis", "signal", "s1", "put", {"id": "s2", "version": 1})


def test_delete_rejects_record(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.add("redis", "signal", "s1", "delete", {"id": "s1", "version": 1})


@pytest.mark.parametrize("seq", [True, "1", 1.0, None])
def test_remove_rejects_non_int_seq(pending_writes, seq):
    with pytest.raises(TypeError):
        pending_writes.remove(seq)


def test_remove_rejects_non_positive_seq(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.remove(0)


def test_mark_failed_rejects_non_string_error(pending_writes):
    seq = pending_writes.add("redis", "signal", "s1", "delete")
    with pytest.raises(TypeError):
        pending_writes.mark_failed(seq, RuntimeError("down"))


def test_pending_rejects_bad_store_filter(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.pending(store="postgres")


def test_pending_rejects_bad_limit(pending_writes):
    with pytest.raises(ValueError):
        pending_writes.pending(limit=0)
    with pytest.raises(TypeError):
        pending_writes.pending(limit="10")


def test_failed_check_writes_nothing(tmp_path):
    path = tmp_path / "pending_writes.json"
    queue = PendingWrites(path)
    with pytest.raises(TypeError):
        queue.add("redis", "signal", "s1", "put", {"id": "s1", "version": "1"})
    assert queue.pending() == []
    assert not path.exists()