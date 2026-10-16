import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import install_error_handlers
from app.records.models import STORE_NAMES
from app.records.pending_writes import PendingWrites
from app.records.replicated import ReplicatedRecords
from app.records.snapshot import SnapshotStore
from app.records.stores import InMemoryStore
from app.signals.builtins import ensure_builtin_signals
from app.signals.routes import router as signals_router

log = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 5

def build_dev_records(data_dir):
    """In-memory stores for local development until the real adapters exist."""
    data_dir = Path(data_dir)
    return ReplicatedRecords(
        [InMemoryStore(name) for name in STORE_NAMES],
        PendingWrites(data_dir / "pending_writes.json"),
        SnapshotStore(data_dir / "snapshot.json"),
    )

async def _sync_forever(records, interval):
    while True:
        await asyncio.sleep(interval)
        try:
            applied = await asyncio.to_thread(records.sync)
            if applied:
                log.info("synced %d pending writes", applied)
        except Exception:
            log.exception("background sync failed")

def _frontend_origins():
    raw = os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

def create_app(records=None, sync_interval=SYNC_INTERVAL_SECONDS):
    if records is None:
        records = build_dev_records(os.environ.get("DATA_DIR", "data"))

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(ensure_builtin_signals, records)
        sync_task = None
        if sync_interval:
            sync_task = asyncio.create_task(_sync_forever(records, sync_interval))
        try:
            yield
        finally:
            if sync_task is not None:
                sync_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sync_task

    app = FastAPI(title="Consistency Under Fire API", lifespan=lifespan)
    app.state.records = records
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Served-By"],
    )
    install_error_handlers(app)
    app.include_router(signals_router)
    return app