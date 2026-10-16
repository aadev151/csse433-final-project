import pytest

from app.records.stores import InMemoryStore, StoreUnavailable

STORE_FACTORIES = {
    "memory": lambda: InMemoryStore("mongodb"),
}


@pytest.fixture(params=sorted(STORE_FACTORIES))
def store(request):
    return STORE_FACTORIES[request.param]()


def make_record(record_id, version=1, **fields):
    return {"id": record_id, "version": version, **fields}


# Contract tests: every store adapter must pass these.

def test_put_then_get_returns_record(store):
    store.put("signal", make_record("s1", name="btc_volume"))
    assert store.get("signal", "s1") == make_record("s1", name="btc_volume")


def test_get_missing_returns_none(store):
    assert store.get("signal", "nope") is None


def test_put_overwrites_existing_record(store):
    store.put("signal", make_record("s1", version=1, name="old"))
    store.put("signal", make_record("s1", version=2, name="new"))
    assert store.get("signal", "s1") == make_record("s1", version=2, name="new")


def test_list_returns_only_that_record_type(store):
    store.put("signal", make_record("s1"))
    store.put("signal", make_record("s2"))
    store.put("experiment", make_record("e1"))
    ids = sorted(record["id"] for record in store.list("signal"))
    assert ids == ["s1", "s2"]


def test_list_empty_type_returns_empty_list(store):
    assert store.list("annotation") == []


def test_delete_removes_record(store):
    store.put("signal", make_record("s1"))
    store.delete("signal", "s1")
    assert store.get("signal", "s1") is None


def test_delete_missing_record_is_not_an_error(store):
    store.delete("signal", "nope")


def test_same_id_in_different_types_does_not_collide(store):
    store.put("signal", make_record("x", name="a signal"))
    store.put("experiment", make_record("x", name="an experiment"))
    assert store.get("signal", "x")["name"] == "a signal"
    assert store.get("experiment", "x")["name"] == "an experiment"


def test_returned_record_is_a_copy(store):
    store.put("signal", make_record("s1", params={"field": "qty"}))
    fetched = store.get("signal", "s1")
    fetched["params"]["field"] = "changed"
    assert store.get("signal", "s1")["params"]["field"] == "qty"


def test_ping_succeeds_when_up(store):
    assert store.ping() >= 0


# Fake-only tests: the down switch that simulates outages.

@pytest.mark.parametrize(
    "operation",
    [
        lambda s: s.put("signal", make_record("s1")),
        lambda s: s.get("signal", "s1"),
        lambda s: s.list("signal"),
        lambda s: s.delete("signal", "s1"),
        lambda s: s.ping(),
    ],
)
def test_down_store_raises_on_every_operation(operation):
    fake = InMemoryStore("cassandra")
    fake.set_down()
    with pytest.raises(StoreUnavailable) as error:
        operation(fake)
    assert error.value.store_name == "cassandra"


def test_store_recovers_after_set_up():
    fake = InMemoryStore("redis")
    fake.put("signal", make_record("s1"))
    fake.set_down()
    fake.set_up()
    assert fake.get("signal", "s1") == make_record("s1")


def test_rejects_unknown_store_name():
    with pytest.raises(ValueError):
        InMemoryStore("postgres")


def test_rejects_record_without_id_or_version():
    fake = InMemoryStore("mongodb")
    with pytest.raises(ValueError):
        fake.put("signal", {"name": "missing id and version"})