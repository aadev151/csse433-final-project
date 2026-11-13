import pytest

from app.records.models import WriteInfo, WriteResponse


def test_committed_when_nothing_pending():
    info = WriteInfo.from_results(written=["mongodb", "cassandra", "redis"], pending=[])
    assert info.status == "committed"
    assert info.stores_pending == []


def test_pending_when_any_store_pending():
    info = WriteInfo.from_results(written=["cassandra", "redis"], pending=["mongodb"])
    assert info.status == "pending"
    assert info.stores_written == ["cassandra", "redis"]
    assert info.stores_pending == ["mongodb"]


def test_store_lists_use_canonical_order():
    info = WriteInfo.from_results(written=["redis", "mongodb"], pending=["cassandra"])
    assert info.stores_written == ["mongodb", "redis"]


def test_rejects_unknown_store():
    with pytest.raises(ValueError):
        WriteInfo.from_results(written=["postgres"], pending=[])


def test_rejects_store_in_both_lists():
    with pytest.raises(ValueError):
        WriteInfo.from_results(written=["mongodb"], pending=["mongodb"])


def test_write_response_with_null_record():
    response = WriteResponse[dict](
        record=None,
        write=WriteInfo.from_results(written=["mongodb", "cassandra", "redis"], pending=[]),
    )
    dumped = response.model_dump()
    assert dumped["record"] is None
    assert dumped["write"]["status"] == "committed"


def test_write_response_with_record():
    response = WriteResponse[dict](
        record={"id": "s1", "name": "btc_volume"},
        write=WriteInfo.from_results(written=["mongodb"], pending=["cassandra", "redis"]),
    )
    dumped = response.model_dump()
    assert dumped["record"]["id"] == "s1"
    assert dumped["write"]["stores_pending"] == ["cassandra", "redis"]