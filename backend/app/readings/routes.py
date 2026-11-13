import csv
import io
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request, Response

from app.errors import not_found, store_down, validation_error
from app.measure.store import fetch_readings

router = APIRouter(prefix="/api/runs", tags=["readings"])
CASSANDRA_DOWN = "Step-by-step readings are stored only in Cassandra, which is down"
FAR_FUTURE_US = 2 ** 62


def _iso(us):
    moment = datetime.fromtimestamp(us / 1_000_000, timezone.utc)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _to_us(text, default):
    if not text:
        return default
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise validation_error(f"{text!r} is not an ISO 8601 timestamp")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1_000_000)


def _run_or_404(request, run_id):
    record, _ = request.app.state.records.get("run", run_id)
    if record is None:
        raise not_found("run", run_id)
    return record


def _session(request):
    for store in request.app.state.records.stores:
        if store.name == "cassandra" and hasattr(store, "_connect"):
            try:
                return store._connect()[0]
            except Exception:
                raise store_down("cassandra_down", CASSANDRA_DOWN)
    raise store_down("cassandra_down", CASSANDRA_DOWN)


def _rows(request, run_id, signal_id, symbol, from_us, to_us):
    session = _session(request)
    try:
        return fetch_readings(session, run_id, signal_id, symbol, from_us, to_us)
    except Exception:
        raise store_down("cassandra_down", CASSANDRA_DOWN)


@router.get("/{run_id}/readings")
def get_readings(
    run_id: str,
    request: Request,
    response: Response,
    signal_id: str,
    symbol: str,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = None,
    max_points: int = Query(default=2000, ge=1, le=20000),
):
    _run_or_404(request, run_id)
    rows = _rows(request, run_id, signal_id, symbol, _to_us(from_, 0), _to_us(to, FAR_FUTURE_US))
    step = max(1, math.ceil(len(rows) / max_points))
    response.headers["X-Served-By"] = "cassandra"
    return {
        "points": [
            {
                "t": _iso(row.t_us),
                "value": row.value,
                "truth": row.truth,
                "staleness_ms": row.staleness_ms,
                "latency_ms": row.latency_ms,
            }
            for row in rows[::step]
        ]
    }


@router.get("/{run_id}/export.csv")
def export_readings(run_id: str, request: Request):
    run = _run_or_404(request, run_id)
    experiment, _ = request.app.state.records.get("experiment", run["experiment_id"])
    signal_ids = experiment.get("signal_ids", []) if experiment else []
    symbols = experiment.get("symbols", []) if experiment else []
    
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["signal_id", "symbol", "t", "market_t", "value", "truth", "staleness_ms", "latency_ms"])
    for signal_id in signal_ids:
        for symbol in symbols:
            for row in _rows(request, run_id, signal_id, symbol, 0, FAR_FUTURE_US):
                writer.writerow([signal_id, symbol, _iso(row.t_us), _iso(row.market_us), row.value, row.truth,
                                 row.staleness_ms, row.latency_ms])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}.csv"'},
    )
