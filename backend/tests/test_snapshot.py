import json

import pytest

from app.records.snapshot import SnapshotStore


@pytest.fixture
def snapshot(tmp_path):
    return SnapshotStore(tmp_path / "snapshot.json")


def test_put_then_get(snapshot):
    snapshot.put("signal", {"id": "s1", "version": 1, "name": "btc_volume"})
    assert snapshot.get("signal", "s1") == {"id": "s1", "version": 1, "name": "btc_volume"}


def test_get_missing_returns_none(snapshot):
    assert snapshot.get("signal", "nope") is None


def test_newer_version_overwrites(snapshot):
    snapshot.put("signal", {"id": "s1", "version": 1, "name": "old"})
    snapshot.put("signal", {"id": "s1", "version": 2, "name": "new"})
    assert snapshot.get("signal", "s1")["name"] == "new"


def test_older_version_does_not_overwrite(snapshot):
    snapshot.put("signal", {"id": "s1", "version": 2, "name": "new"})
    snapshot.put("signal", {"id": "s1", "version": 1, "name": "old"})
    assert snapshot.get("signal", "s1")["name"] == "new"


def test_list_by_type(snapshot):
    snapshot.put("signal", {"id": "s1", "version": 1})
    snapshot.put("experiment", {"id": "e1", "version": 1})
    assert [record["id"] for record in snapshot.list("signal")] == ["s1"]


def test_delete(snapshot):
    snapshot.put("signal", {"id": "s1", "version": 1})
    snapshot.delete("signal", "s1")
    assert snapshot.get("signal", "s1") is None


def test_delete_missing_is_not_an_error(snapshot):
    snapshot.delete("signal", "nope")


def test_survives_reopen(tmp_path):
    path = tmp_path / "snapshot.json"
    SnapshotStore(path).put("signal", {"id": "s1", "version": 1})
    assert SnapshotStore(path).get("signal", "s1") == {"id": "s1", "version": 1}


def test_file_is_valid_json_with_no_leftover_temp_file(tmp_path):
    path = tmp_path / "snapshot.json"
    SnapshotStore(path).put("signal", {"id": "s1", "version": 1})
    assert json.loads(path.read_text())["signal"]["s1"]["version"] == 1
    assert [p.name for p in tmp_path.iterdir()] == ["snapshot.json"]


def test_corrupt_file_is_set_aside(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("not json {")
    store = SnapshotStore(path)
    assert store.list("signal") == []
    assert any(p.name.startswith("snapshot.json.corrupt-") for p in tmp_path.iterdir())


def test_wrong_shape_file_is_set_aside(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"signal": ["not", "an", "object"]}))
    store = SnapshotStore(path)
    assert store.list("signal") == []
    assert any(p.name.startswith("snapshot.json.corrupt-") for p in tmp_path.iterdir())


def test_returned_record_is_a_copy(snapshot):
    snapshot.put("signal", {"id": "s1", "version": 1, "params": {"field": "qty"}})
    fetched = snapshot.get("signal", "s1")
    fetched["params"]["field"] = "changed"
    assert snapshot.get("signal", "s1")["params"]["field"] == "qty"


# Parameter checks

def test_rejects_record_without_id_or_version(snapshot):
    with pytest.raises(ValueError):
        snapshot.put("signal", {"name": "no id"})


def test_rejects_unknown_record_type(snapshot):
    with pytest.raises(ValueError):
        snapshot.put("users", {"id": "u1", "version": 1})
    with pytest.raises(ValueError):
        snapshot.get("users", "u1")


def test_rejects_wrong_field_types(snapshot):
    with pytest.raises(TypeError):
        snapshot.put("signal", {"id": "s1", "version": "1"})
    with pytest.raises(TypeError):
        snapshot.put("signal", ("s1", 1))


def test_get_and_delete_reject_non_string_id(snapshot):
    with pytest.raises(TypeError):
        snapshot.get("signal", 1)
    with pytest.raises(TypeError):
        snapshot.delete("signal", None)


def test_rejects_non_json_record(snapshot):
    with pytest.raises(ValueError):
        snapshot.put("signal", {"id": "s1", "version": 1, "bad": {1, 2}})


def test_failed_check_writes_nothing(tmp_path):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    with pytest.raises(TypeError):
        store.put("signal", {"id": "s1", "version": "1"})
    assert not path.exists()