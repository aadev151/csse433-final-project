from datetime import datetime, timezone

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api", tags=["health"])


def _check(store):
    try:
        return {"up": True, "latency_ms": round(store.ping(), 1)}
    except Exception:
        return {"up": False, "latency_ms": None}


@router.get("/health")
def get_health(request: Request):
    records = request.app.state.records
    stores = {store.name: _check(store) for store in records.stores}
    stores["cassandra"]["nodes"] = []
    
    up_count = sum(1 for store in stores.values() if store["up"])
    if up_count == len(stores):
        mode = "normal"
    elif up_count == 0:
        mode = "offline"
    else:
        mode = "degraded"
    
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "stores": stores,
        "pending_writes": records.pending_counts(),
    }
