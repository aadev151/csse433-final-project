from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.datasets.importer import DatasetImporter
from app.main import create_app
from app.records.models import STORE_NAMES
from app.records.pending_writes import PendingWrites
from app.records.replicated import ReplicatedRecords
from app.records.snapshot import SnapshotStore
from app.records.stores import InMemoryStore
from tests.dataset_helpers import FakeFetcher

TODAY = date(2024, 1, 10)
DATASET_KEYS = {
    "id", "symbol", "kind", "day", "status", "row_count", "size_bytes",
    "checksum_ok", "error", "created_at", "version",
}


@pytest.fixture
def env(tmp_path):
    stores = {name: InMemoryStore(name) for name in STORE_NAMES}
    records = ReplicatedRecords(
        [stores[name] for name in STORE_NAMES],
        PendingWrites(tmp_path / "pending_writes.json"),
        SnapshotStore(tmp_path / "snapshot.json"),
    )
    fetcher = FakeFetcher()
    importer = DatasetImporter(records, tmp_path, fetcher=fetcher, today=lambda: TODAY, run_inline=True)
    app = create_app(records=records, importer=importer, sync_interval=None)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, fetcher=fetcher, stores=stores)


def import_body(**overrides):
    body = {"symbol": "BTCUSDT", "kind": "trades", "start": "2024-01-01", "end": "2024-01-02"}
    body.update(overrides)
    return body


def test_import_returns_one_record_per_day_in_contract_shape(env):
    env.fetcher.publish("BTCUSDT", date(2024, 1, 1))
    env.fetcher.publish("BTCUSDT", date(2024, 1, 2))
    response = env.client.post("/api/datasets/import", json=import_body())
    assert response.status_code == 200
    body = response.json()
    assert [record["day"] for record in body["records"]] == ["2024-01-01", "2024-01-02"]
    assert all(set(record) == DATASET_KEYS for record in body["records"])
    assert all(record["status"] == "downloading" for record in body["records"])
    assert body["write"]["status"] == "committed"


def test_list_shows_finished_imports_with_served_by(env):
    env.fetcher.publish("BTCUSDT", date(2024, 1, 1))
    env.client.post("/api/datasets/import", json=import_body(end="2024-01-01"))
    response = env.client.get("/api/datasets")
    assert response.headers["X-Served-By"] == "mongodb"
    assert [(dataset["id"], dataset["status"]) for dataset in response.json()] == [
        ("BTCUSDT-trades-2024-01-01", "ready")
    ]


def test_import_with_store_down_reports_pending(env):
    env.fetcher.publish("BTCUSDT", date(2024, 1, 1))
    env.stores["redis"].set_down()
    body = env.client.post("/api/datasets/import", json=import_body(end="2024-01-01")).json()
    assert body["write"]["status"] == "pending"
    assert body["write"]["stores_pending"] == ["redis"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"end": "2023-12-31"},                     # end before start
        {"start": "2023-11-01", "end": "2024-01-02"},  # more than 31 days
        {"start": "2024-1-01"},                    # wrong format
        {"start": "2024-02-30", "end": "2024-03-01"},  # not a real date
        {"start": 20240101},                       # not a string
        {"symbol": "DOGEUSDT"},
        {"kind": "quotes"},
        {"kind": "orders"},
        {"end": "2024-01-10"},                     # not published yet
        {"extra": "field"},
    ],
)
def test_import_rejects_invalid_requests(env, overrides):
    response = env.client.post("/api/datasets/import", json=import_body(**overrides))
    assert response.status_code == 422
    assert response.json()["reason"] == "validation"


def test_quotes_error_explains_why(env):
    response = env.client.post("/api/datasets/import", json=import_body(kind="quotes"))
    assert "Quote data" in response.json()["message"]


def test_delete_dataset(env):
    env.fetcher.publish("BTCUSDT", date(2024, 1, 1))
    env.client.post("/api/datasets/import", json=import_body(end="2024-01-01"))
    response = env.client.delete("/api/datasets/BTCUSDT-trades-2024-01-01")
    assert response.status_code == 200
    assert response.json()["record"] is None
    assert env.client.get("/api/datasets").json() == []


def test_delete_missing_is_404(env):
    response = env.client.delete("/api/datasets/BTCUSDT-trades-2024-01-01")
    assert response.status_code == 404
    assert response.json()["reason"] == "not_found"