import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import load_settings
from app.errors import install_error_handlers
from app.records.models import STORE_NAMES
from app.records.pending_writes import PendingWrites
from app.records.replicated import ReplicatedRecords
from app.records.snapshot import SnapshotStore
from app.records.stores import InMemoryStore
from app.signals.builtins import ensure_builtin_signals
from app.signals.routes import router as signals_router
from app.annotations.routes import router as annotations_router
from app.db.cassandra_store import CassandraStore
from app.db.mongo_store import MongoStore
from app.db.redis_store import RedisStore
from app.experiments.routes import router as experiments_router
from app.runs.routes import router as runs_router


log = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 5


def build_stores(settings):
    if settings.store_mode == "memory":
        return [InMemoryStore(name) for name in STORE_NAMES]

    timeout = settings.store_timeout_seconds
    timeout_ms = int(timeout * 1000)

    mongo = MongoStore(
        uri=settings.mongo_uri,
        database_name=settings.mongo_db,
        timeout_ms=timeout_ms,
    )

    cassandra = CassandraStore(
        hosts=settings.cassandra_hosts,
        port=settings.cassandra_port,
        keyspace=settings.cassandra_keyspace,
        local_dc=settings.cassandra_local_dc,
        consistency=settings.cassandra_consistency,
        timeout_seconds=timeout,
    )

    redis_store = RedisStore(
        url=settings.redis_url,
        timeout_seconds=timeout,
    )

    return [mongo, cassandra, redis_store]


def build_records(settings):
    data_dir = Path(settings.data_dir)
    return ReplicatedRecords(
        build_stores(settings),
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


def _close_stores(records):
    for store in records.stores:
        close = getattr(store, "close", None)
        if close is None:
            continue
        try:
            close()
        except Exception:
            log.exception("failed to close %s", store.name)


def create_app(records=None, settings=None, sync_interval=SYNC_INTERVAL_SECONDS):
    if settings is None:
        settings = load_settings()
    if records is None:
        records = build_records(settings)

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
            await asyncio.to_thread(_close_stores, records)

    app = FastAPI(title="Consistency Under Fire API", lifespan=lifespan)
    app.state.records = records
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Served-By"],
    )
    install_error_handlers(app)
    app.include_router(signals_router)
    app.include_router(annotations_router)
    app.include_router(experiments_router)
    app.include_router(runs_router)
    return app