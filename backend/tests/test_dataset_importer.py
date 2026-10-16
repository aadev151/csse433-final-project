from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.datasets.importer import DatasetImporter, ImportRequestInvalid
from app.records.models import STORE_NAMES
from app.records.pending_writes import PendingWrites
from app.records.replicated import RecordNotFound, ReplicatedRecords
from app.records.snapshot import SnapshotStore
from app.records.stores import InMemoryStore
from tests.dataset_helpers import FakeFetcher, trade_rows, zip_bytes

DAY = date(2024, 1, 1)
TODAY = date(2024, 1, 10)


@pytest.fixture
def env(tmp_path):
    records = ReplicatedRecords(
        [InMemoryStore(name) for name in STORE_NAMES],
        PendingWrites(tmp_path / "pending_writes.json"),
        SnapshotStore(tmp_path / "snapshot.json"),
    )
    fetcher = FakeFetcher()
    importer = DatasetImporter(records, tmp_path, fetcher=fetcher, today=lambda: TODAY, run_inline=True)
    return SimpleNamespace(records=records, fetcher=fetcher, importer=importer, root=tmp_path / "binance")


def get(env, record_id):
    return env.records.get("dataset", record_id)[0]


def zip_path(env, day=DAY):
    return env.root / "BTCUSDT" / "trades" / f"BTCUSDT-trades-{day.isoformat()}.zip"


def test_import_one_day_ends_ready(env):
    env.fetcher.publish("BTCUSDT", DAY, rows=trade_rows(DAY, count=5))
    records, writes = env.importer.start_import("BTCUSDT", "trades", [DAY])
    assert [record["status"] for record in records] == ["downloading"]
    assert writes[0].status == "committed"

    record = get(env, "BTCUSDT-trades-2024-01-01")
    assert record["status"] == "ready"
    assert record["row_count"] == 5
    assert record["checksum_ok"] is True
    assert record["timestamp_unit"] == "ms"
    assert record["size_bytes"] == zip_path(env).stat().st_size
    assert record["error"] is None
    assert record["version"] == 3  # downloading -> verifying -> ready


def test_range_creates_one_record_per_day_and_reports_missing_days(env):
    day2 = DAY + timedelta(days=1)
    env.fetcher.publish("BTCUSDT", DAY)
    records, _ = env.importer.start_import("BTCUSDT", "trades", [DAY, day2])
    assert [record["day"] for record in records] == ["2024-01-01", "2024-01-02"]
    assert get(env, "BTCUSDT-trades-2024-01-01")["status"] == "ready"
    missing = get(env, "BTCUSDT-trades-2024-01-02")
    assert missing["status"] == "failed"
    assert "no trades file" in missing["error"]


def test_checksum_mismatch_fails_and_removes_file(env):
    env.fetcher.publish("BTCUSDT", DAY, checksum="0" * 64)
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    record = get(env, "BTCUSDT-trades-2024-01-01")
    assert record["status"] == "failed"
    assert record["checksum_ok"] is False
    assert "Checksum mismatch" in record["error"]
    assert not zip_path(env).exists()


def test_invalid_contents_fail_with_checksum_ok(env):
    rows = trade_rows(DAY)
    rows[1][1] = "abc"
    env.fetcher.publish("BTCUSDT", DAY, data=zip_bytes(rows))
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    record = get(env, "BTCUSDT-trades-2024-01-01")
    assert record["status"] == "failed"
    assert record["checksum_ok"] is True
    assert "failed validation" in record["error"]


def test_missing_checksum_file_fails(env):
    env.fetcher.publish("BTCUSDT", DAY)
    del env.fetcher.files[[url for url in env.fetcher.files if url.endswith(".CHECKSUM")][0]]
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    assert "no checksum file" in get(env, "BTCUSDT-trades-2024-01-01")["error"]


def test_reimporting_ready_day_does_not_download_again(env):
    env.fetcher.publish("BTCUSDT", DAY)
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    records, writes = env.importer.start_import("BTCUSDT", "trades", [DAY])
    assert records[0]["status"] == "ready"
    assert writes == []
    assert len(env.fetcher.downloads) == 1


def test_reimporting_failed_day_retries(env):
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    assert get(env, "BTCUSDT-trades-2024-01-01")["status"] == "failed"
    env.fetcher.publish("BTCUSDT", DAY)
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    record = get(env, "BTCUSDT-trades-2024-01-01")
    assert record["status"] == "ready"
    assert record["error"] is None


@pytest.mark.parametrize("day", [TODAY, TODAY + timedelta(days=5)])
def test_rejects_days_not_yet_published(env, day):
    with pytest.raises(ImportRequestInvalid):
        env.importer.start_import("BTCUSDT", "trades", [day])


def test_recover_interrupted_marks_in_progress_as_failed(env):
    env.records.create(
        "dataset",
        {**env.importer._fresh_fields("BTCUSDT", "trades", DAY), "status": "verifying"},
        record_id="BTCUSDT-trades-2024-01-01",
    )
    env.importer.recover_interrupted()
    record = get(env, "BTCUSDT-trades-2024-01-01")
    assert record["status"] == "failed"
    assert "interrupted" in record["error"]


def test_delete_removes_record_and_file(env):
    env.fetcher.publish("BTCUSDT", DAY)
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    assert zip_path(env).exists()
    write = env.importer.delete("BTCUSDT-trades-2024-01-01")
    assert write.status == "committed"
    assert get(env, "BTCUSDT-trades-2024-01-01") is None
    assert not zip_path(env).exists()


def test_delete_missing_raises(env):
    with pytest.raises(RecordNotFound):
        env.importer.delete("BTCUSDT-trades-2024-01-01")


def test_delete_during_import_does_not_crash_or_leave_file(env):
    env.fetcher.publish("BTCUSDT", DAY)
    env.fetcher.on_download = lambda url: env.records.delete("dataset", "BTCUSDT-trades-2024-01-01")
    env.importer.start_import("BTCUSDT", "trades", [DAY])
    assert get(env, "BTCUSDT-trades-2024-01-01") is None
    assert not zip_path(env).exists()