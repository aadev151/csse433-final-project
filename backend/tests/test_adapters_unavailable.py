import pytest

from app.db.cassandra_store import CassandraStore
from app.db.mongo_store import MongoStore
from app.db.redis_store import RedisStore
from app.records.stores import StoreUnavailable

RECORD = {"id": "s1", "version": 1}

OPERATIONS = [
    lambda s: s.put("signal", RECORD),
    lambda s: s.get("signal", "s1"),
    lambda s: s.list("signal"),
    lambda s: s.delete("signal", "s1"),
    lambda s: s.ping(),
]


def unreachable_mongo():
    return MongoStore.connect("mongodb://127.0.0.1:1/?directConnection=true", timeout_ms=300)


def unreachable_cassandra():
    return CassandraStore(["127.0.0.1"], port=1, timeout_seconds=0.5)


def unreachable_redis():
    return RedisStore.from_url("redis://127.0.0.1:1/0", timeout_seconds=0.5)


@pytest.mark.parametrize("make_store", [unreachable_mongo, unreachable_cassandra, unreachable_redis])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_unreachable_store_raises_store_unavailable(make_store, operation):
    store = make_store()
    try:
        with pytest.raises(StoreUnavailable) as error:
            operation(store)
        assert error.value.store_name == store.name
    finally:
        store.close()


@pytest.mark.parametrize("make_store", [unreachable_mongo, unreachable_cassandra, unreachable_redis])
def test_checks_run_before_any_network_call(make_store):
    store = make_store()
    try:
        with pytest.raises(ValueError):
            store.get("users", "u1")
        with pytest.raises(TypeError):
            store.get("signal", 1)
        with pytest.raises(TypeError):
            store.put("signal", {"id": "s1", "version": "1"})
    finally:
        store.close()


@pytest.mark.parametrize("name", ["App", "1app", "app-test", "app;drop", ""])
def test_cassandra_rejects_bad_keyspace(name):
    with pytest.raises((ValueError, TypeError)):
        CassandraStore(["127.0.0.1"], keyspace=name)


def test_cassandra_rejects_bad_consistency():
    with pytest.raises(ValueError):
        CassandraStore(["127.0.0.1"], consistency="SOME")


@pytest.mark.parametrize("prefix", ["App", "1app", "app:x", "app x", ""])
def test_redis_rejects_bad_prefix(prefix):
    with pytest.raises((ValueError, TypeError)):
        RedisStore.from_url("redis://127.0.0.1:1/0", key_prefix=prefix)


@pytest.mark.parametrize("name", ["", "1db", "db.name", "db$"])
def test_mongo_rejects_bad_database_name(name):
    with pytest.raises((ValueError, TypeError)):
        MongoStore.connect("mongodb://127.0.0.1:1", database_name=name)