import os
import uuid
from contextlib import contextmanager

import pytest

from app.records.stores import InMemoryStore, StoreUnavailable


@contextmanager
def memory_store():
    yield InMemoryStore("mongodb")


@contextmanager
def mongo_store():
    from pymongo import MongoClient

    from app.db.mongo_store import MongoStore

    uri = os.environ["TEST_MONGO_URI"]
    database = f"test_{uuid.uuid4().hex[:8]}"
    store = MongoStore.connect(uri, database_name=database)
    try:
        yield store
    finally:
        store.close()
        cleanup = MongoClient(uri)
        cleanup.drop_database(database)
        cleanup.close()


@contextmanager
def cassandra_store():
    from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile
    from cassandra.policies import DCAwareRoundRobinPolicy

    from app.db.cassandra_store import CassandraStore

    hosts = os.environ["TEST_CASSANDRA_HOSTS"].split(",")
    admin_profile = ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="dc1"))
    admin_cluster = Cluster(hosts, execution_profiles={EXEC_PROFILE_DEFAULT: admin_profile})
    admin = admin_cluster.connect()
    # Test-only setup: the app itself never runs DDL.
    admin.execute(
        "CREATE KEYSPACE IF NOT EXISTS app_test "
        "WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 1}"
    )
    admin.execute(
        "CREATE TABLE IF NOT EXISTS app_test.records ("
        "record_type text, id text, version int, body text, "
        "PRIMARY KEY ((record_type), id))"
    )
    admin.execute("TRUNCATE app_test.records")
    store = CassandraStore(hosts, keyspace="app_test", consistency="ONE")
    try:
        yield store
    finally:
        store.close()
        admin_cluster.shutdown()


@contextmanager
def redis_store():
    from app.db.redis_store import RedisStore

    prefix = f"test_{uuid.uuid4().hex[:8]}"
    store = RedisStore.from_url(os.environ["TEST_REDIS_URL"], key_prefix=prefix)
    try:
        yield store
    finally:
        for key in store._client.scan_iter(f"{prefix}:*"):
            store._client.delete(key)
        store.close()


STORE_FACTORIES = {"memory": memory_store}
if os.environ.get("TEST_MONGO_URI"):
    STORE_FACTORIES["mongodb"] = mongo_store
if os.environ.get("TEST_CASSANDRA_HOSTS"):
    STORE_FACTORIES["cassandra"] = cassandra_store
if os.environ.get("TEST_REDIS_URL"):
    STORE_FACTORIES["redis"] = redis_store


@pytest.fixture(params=sorted(STORE_FACTORIES))
def store(request):
    with STORE_FACTORIES[request.param]() as created:
        yield created


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
    assert store.list("signal") == []


def test_delete_missing_record_is_not_an_error(store):
    store.delete("signal", "nope")


def test_same_id_in_different_types_does_not_collide(store):
    store.put("signal", make_record("x", name="a signal"))
    store.put("experiment", make_record("x", name="an experiment"))
    assert store.get("signal", "x")["name"] == "a signal"
    assert store.get("experiment", "x")["name"] == "an experiment"


def test_nested_fields_round_trip(store):
    record = make_record("s1", params={"field": "qty", "side": "net"}, inputs=["trades", "quotes"])
    store.put("signal", record)
    assert store.get("signal", "s1") == record


def test_returned_record_is_a_copy(store):
    store.put("signal", make_record("s1", params={"field": "qty"}))
    fetched = store.get("signal", "s1")
    fetched["params"]["field"] = "changed"
    assert store.get("signal", "s1")["params"]["field"] == "qty"


def test_rejects_unknown_record_type(store):
    with pytest.raises(ValueError):
        store.get("users", "u1")


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