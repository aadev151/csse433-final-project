import hashlib
import io
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.datasets import importer
from app.main import create_app
from app.measure.execute import find_market_file
from app.records.models import STORE_NAMES
from app.records.pending_writes import PendingWrites
from app.records.replicated import ReplicatedRecords
from app.records.snapshot import SnapshotStore
from app.records.stores import InMemoryStore

SPOT_TRADES = "https://data.binance.vision/data/spot/daily/trades"
FUTURES_BOOK_TICKER = "https://data.binance.vision/data/futures/um/daily/bookTicker"


class FakeResponse(io.BytesIO):
    """Stands in for what urlopen returns. Can blow up after some reads to fake a dropped connection."""

    def __init__(self, data, fail_after_reads=None):
        super().__init__(data)
        self.fail_after_reads = fail_after_reads
        self.reads = 0

    def read(self, size=-1):
        if self.fail_after_reads is not None and self.reads >= self.fail_after_reads:
            raise TimeoutError("timed out")
        self.reads += 1
        return super().read(size)


class FakeBinance:
    """Fake data.binance.vision: url -> bytes. Unknown urls return 404 like the real site."""

    def __init__(self):
        self.files = {}
        self.broken = {}
        self.requested = []
        self.unreachable = False

    def add(self, url, data, checksum=None):
        name = url.rsplit("/", 1)[1]
        checksum = checksum or hashlib.sha256(data).hexdigest()
        self.files[url] = data
        self.files[url + ".CHECKSUM"] = f"{checksum}  {name}\n".encode()

    def urlopen(self, url, timeout=None):
        assert timeout is not None, "every download needs a timeout"
        self.requested.append(url)
        if self.unreachable:
            raise URLError("no route to host")
        if url in self.broken:
            return FakeResponse(self.files[url], fail_after_reads=self.broken[url])
        if url not in self.files:
            raise HTTPError(url, 404, "Not Found", None, None)
        return FakeResponse(self.files[url])


@pytest.fixture
def env(tmp_path, monkeypatch):
    stores = {name: InMemoryStore(name) for name in STORE_NAMES}
    records = ReplicatedRecords(
        [stores[name] for name in STORE_NAMES],
        PendingWrites(tmp_path / "pending_writes.json"),
        SnapshotStore(tmp_path / "snapshot.json"),
    )
    raw = tmp_path / "raw-data"
    other = tmp_path / "testing"
    raw.mkdir()
    other.mkdir()
    settings = Settings(data_dir=str(tmp_path), raw_data_dirs=(str(raw), str(other)))

    binance = FakeBinance()
    monkeypatch.setattr(importer, "urlopen", binance.urlopen)

    client = TestClient(create_app(records=records, settings=settings, sync_interval=0))
    return SimpleNamespace(client=client, records=records, stores=stores, raw=raw, other=other, binance=binance)


def stored_datasets(env, store="mongodb"):
    return {record["id"]: record for record in env.stores[store].list("dataset")}


def files_in(folder):
    return sorted(path.name for path in folder.iterdir())


def trades_url(symbol, day):
    return f"{SPOT_TRADES}/{symbol}/{symbol}-trades-{day}.zip"


def quotes_url(symbol, day):
    return f"{FUTURES_BOOK_TICKER}/{symbol}/{symbol}-bookTicker-{day}.zip"


# Successful imports

def test_import_trades_for_a_day_range(env):
    env.binance.add(trades_url("SOLUSDT", "2024-01-01"), b"day one")
    env.binance.add(trades_url("SOLUSDT", "2024-01-02"), b"day two!!")

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-02"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["failed"] == []
    assert body["write"] == {"status": "committed", "stores_written": list(STORE_NAMES), "stores_pending": []}
    assert [record["id"] for record in body["records"]] == ["SOLUSDT-trades-2024-01-01", "SOLUSDT-trades-2024-01-02"]

    first = body["records"][0]
    assert first["symbol"] == "SOLUSDT"
    assert first["kind"] == "trades"
    assert first["day"] == "2024-01-01"
    assert first["status"] == "ready"
    assert first["size_bytes"] == len(b"day one")
    assert first["checksum_ok"] is True
    assert first["error"] is None
    assert first["version"] == 1

    assert files_in(env.raw) == [
        "SOLUSDT-trades-2024-01-01.zip",
        "SOLUSDT-trades-2024-01-01.zip.CHECKSUM",
        "SOLUSDT-trades-2024-01-02.zip",
        "SOLUSDT-trades-2024-01-02.zip.CHECKSUM",
    ]
    assert (env.raw / "SOLUSDT-trades-2024-01-02.zip").read_bytes() == b"day two!!"
    expected_sum = hashlib.sha256(b"day one").hexdigest()
    assert (env.raw / "SOLUSDT-trades-2024-01-01.zip.CHECKSUM").read_text() == f"{expected_sum}  SOLUSDT-trades-2024-01-01.zip\n"
    # nothing goes into the second raw-data folder
    assert files_in(env.other) == []


def test_import_writes_exactly_one_record_per_day_to_every_store(env):
    env.binance.add(trades_url("SOLUSDT", "2024-01-01"), b"a")
    env.binance.add(trades_url("SOLUSDT", "2024-01-02"), b"bb")
    env.binance.add(trades_url("SOLUSDT", "2024-01-03"), b"ccc")

    env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-03"},
    )

    for store in STORE_NAMES:
        records = stored_datasets(env, store)
        assert sorted(records) == [
            "SOLUSDT-trades-2024-01-01",
            "SOLUSDT-trades-2024-01-02",
            "SOLUSDT-trades-2024-01-03",
        ]
        assert records["SOLUSDT-trades-2024-01-03"]["size_bytes"] == 3
        for record in records.values():
            assert {"symbol", "kind", "day", "size_bytes", "checksum_ok", "status"} <= set(record)
            assert record["version"] == 1


def test_import_quotes_uses_futures_book_ticker_and_file_naming(env):
    env.binance.add(quotes_url("BTCUSDT", "2024-03-01"), b"quotes!")

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "BTCUSDT", "kind": "quotes", "start": "2024-03-01", "end": "2024-03-01"},
    )

    assert response.status_code == 200
    record = response.json()["records"][0]
    assert record["id"] == "BTCUSDT-quotes-2024-03-01"
    assert record["kind"] == "quotes"
    assert env.binance.requested == [
        quotes_url("BTCUSDT", "2024-03-01") + ".CHECKSUM",
        quotes_url("BTCUSDT", "2024-03-01"),
    ]
    # replay looks files up by the Binance name, so it must find the new file
    path = find_market_file((str(env.raw), str(env.other)), "BTCUSDT", "bookTicker", "2024-03-01")
    assert path == env.raw / "BTCUSDT-bookTicker-2024-03-01.zip"


def test_imported_file_shows_up_in_list(env):
    env.binance.add(trades_url("ETHUSDT", "2024-02-02"), b"12345")
    env.client.post(
        "/api/datasets/import",
        json={"symbol": "ETHUSDT", "kind": "trades", "start": "2024-02-02", "end": "2024-02-02"},
    )

    listed = env.client.get("/api/datasets").json()

    assert [(d["id"], d["size_bytes"], d["status"]) for d in listed] == [("ETHUSDT-trades-2024-02-02", 5, "ready")]


def test_write_is_pending_when_a_store_is_down(env):
    env.stores["redis"].set_down()
    env.binance.add(trades_url("SOLUSDT", "2024-01-01"), b"a")

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-01"},
    )

    assert response.status_code == 200
    assert response.json()["write"] == {
        "status": "pending",
        "stores_written": ["mongodb", "cassandra"],
        "stores_pending": ["redis"],
    }


# Verification failures

def test_checksum_mismatch_saves_nothing(env):
    env.binance.add(trades_url("SOLUSDT", "2024-01-01"), b"tampered", checksum="0" * 64)

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-01"},
    )

    assert response.status_code == 502
    assert response.json()["reason"] == "download_failed"
    assert "Checksum mismatch" in response.json()["message"]
    assert files_in(env.raw) == []
    assert stored_datasets(env) == {}


def test_download_cut_off_midway_leaves_no_partial_file(env, monkeypatch):
    monkeypatch.setattr(importer, "CHUNK_SIZE", 4)
    url = trades_url("SOLUSDT", "2024-01-01")
    env.binance.add(url, b"0123456789abcdef")
    env.binance.broken[url] = 2  # two chunks arrive, then the connection times out

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-01"},
    )

    assert response.status_code == 502
    assert "timed out" in response.json()["message"]
    assert files_in(env.raw) == []
    assert stored_datasets(env) == {}


def test_missing_day_on_binance_is_reported(env):
    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "BTCUSDT", "kind": "quotes", "start": "2025-01-01", "end": "2025-01-01"},
    )

    assert response.status_code == 502
    assert "Binance has no quotes file for BTCUSDT on 2025-01-01" in response.json()["message"]
    assert files_in(env.raw) == []


def test_bad_checksum_file_is_rejected(env):
    url = trades_url("SOLUSDT", "2024-01-01")
    env.binance.files[url] = b"data"
    env.binance.files[url + ".CHECKSUM"] = b"<html>not a checksum</html>"

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-01"},
    )

    assert response.status_code == 502
    assert "not valid" in response.json()["message"]
    assert files_in(env.raw) == []


def test_binance_unreachable(env):
    env.binance.unreachable = True

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-01"},
    )

    assert response.status_code == 502
    assert "Could not reach Binance" in response.json()["message"]
    assert files_in(env.raw) == []


def test_some_days_fail_and_others_still_import(env):
    env.binance.add(trades_url("SOLUSDT", "2024-01-01"), b"good")
    env.binance.add(trades_url("SOLUSDT", "2024-01-03"), b"bad", checksum="f" * 64)
    # 2024-01-02 is missing on Binance

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-03"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [record["id"] for record in body["records"]] == ["SOLUSDT-trades-2024-01-01"]
    assert [item["day"] for item in body["failed"]] == ["2024-01-02", "2024-01-03"]
    assert "Checksum mismatch" in body["failed"][1]["error"]
    assert files_in(env.raw) == ["SOLUSDT-trades-2024-01-01.zip", "SOLUSDT-trades-2024-01-01.zip.CHECKSUM"]
    assert sorted(stored_datasets(env)) == ["SOLUSDT-trades-2024-01-01"]


# Already imported days

def test_all_days_already_on_disk_is_a_validation_error(env):
    (env.raw / "SOLUSDT-trades-2024-01-01.zip").write_bytes(b"x")
    (env.other / "SOLUSDT-trades-2024-01-02.zip").write_bytes(b"x")

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-02"},
    )

    assert response.status_code == 422
    assert response.json() == {"reason": "validation", "message": "All of those days are already imported."}
    assert env.binance.requested == []


def test_only_missing_days_are_downloaded(env):
    (env.raw / "SOLUSDT-trades-2024-01-01.zip").write_bytes(b"x")
    env.binance.add(trades_url("SOLUSDT", "2024-01-02"), b"new")

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-02"},
    )

    assert response.status_code == 200
    assert [record["day"] for record in response.json()["records"]] == ["2024-01-02"]
    assert all("2024-01-01" not in url for url in env.binance.requested)


def test_trades_on_disk_does_not_block_quotes_for_same_day(env):
    (env.raw / "SOLUSDT-trades-2024-01-01.zip").write_bytes(b"x")
    env.binance.add(quotes_url("SOLUSDT", "2024-01-01"), b"q")

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "quotes", "start": "2024-01-01", "end": "2024-01-01"},
    )

    assert response.status_code == 200
    assert response.json()["records"][0]["id"] == "SOLUSDT-quotes-2024-01-01"


# Bad request bodies

@pytest.mark.parametrize(
    "body, message",
    [
        ({"symbol": "DOGEUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-01"}, "symbol"),
        ({"symbol": "BTCUSDT", "kind": "bookTicker", "start": "2024-01-01", "end": "2024-01-01"}, "kind"),
        ({"symbol": "BTCUSDT", "kind": "trades", "start": "2024-13-01", "end": "2024-01-01"}, "start"),
        ({"symbol": "BTCUSDT", "kind": "trades", "start": "2024-01-01"}, "end"),
        ({"symbol": "BTCUSDT", "kind": "trades", "start": "2024-01-05", "end": "2024-01-01"}, "End date is before start date."),
        ({"symbol": "BTCUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-02-01"}, "Import at most 31 days at a time."),
    ],
)
def test_invalid_import_bodies_are_rejected(env, body, message):
    response = env.client.post("/api/datasets/import", json=body)

    assert response.status_code == 422
    assert response.json()["reason"] == "validation"
    assert message in response.json()["message"]
    assert env.binance.requested == []


def test_exactly_31_days_is_allowed(env):
    for day in range(1, 32):
        env.binance.add(trades_url("SOLUSDT", f"2024-01-{day:02d}"), b"x")

    response = env.client.post(
        "/api/datasets/import",
        json={"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-31"},
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 31


# Delete

def test_delete_removes_files_from_every_raw_data_folder(env):
    env.binance.add(quotes_url("ETHUSDT", "2024-01-01"), b"q")
    env.client.post(
        "/api/datasets/import",
        json={"symbol": "ETHUSDT", "kind": "quotes", "start": "2024-01-01", "end": "2024-01-01"},
    )
    (env.other / "ETHUSDT-bookTicker-2024-01-01.zip").write_bytes(b"older copy")
    (env.raw / "ETHUSDT-trades-2024-01-01.zip").write_bytes(b"keep me")

    response = env.client.delete("/api/datasets/ETHUSDT-quotes-2024-01-01")

    assert response.status_code == 200
    assert response.json()["record"] is None
    assert response.json()["write"]["status"] == "committed"
    assert files_in(env.raw) == ["ETHUSDT-trades-2024-01-01.zip"]
    assert files_in(env.other) == []
    assert [d["id"] for d in env.client.get("/api/datasets").json()] == ["ETHUSDT-trades-2024-01-01"]


@pytest.mark.parametrize(
    "dataset_id",
    ["ETHUSDT-quotes-2024-01-01", "ETHUSDT-bookTicker-2024-01-01", "nonsense", "..-trades-2024-01-01"],
)
def test_delete_unknown_dataset_is_404(env, dataset_id):
    response = env.client.delete(f"/api/datasets/{dataset_id}")

    assert response.status_code == 404
    assert response.json()["reason"] == "not_found"


def test_import_again_after_delete_puts_the_file_back(env):
    # Until DELETE also removes the record, the old record is reused instead of crashing.
    env.binance.add(trades_url("SOLUSDT", "2024-01-01"), b"a")
    body = {"symbol": "SOLUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-01"}
    env.client.post("/api/datasets/import", json=body)
    env.client.delete("/api/datasets/SOLUSDT-trades-2024-01-01")

    response = env.client.post("/api/datasets/import", json=body)

    assert response.status_code == 422
    assert files_in(env.raw) == ["SOLUSDT-trades-2024-01-01.zip", "SOLUSDT-trades-2024-01-01.zip.CHECKSUM"]
    assert sorted(stored_datasets(env)) == ["SOLUSDT-trades-2024-01-01"]
