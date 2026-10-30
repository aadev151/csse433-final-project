import logging

from fastapi import APIRouter, Request

from app.errors import not_found, store_down
from app.records.models import STORE_NAMES


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


@router.post("/replay/{store_name}")
def replay_store(store_name: str, request: Request):
    if store_name not in STORE_NAMES:
        raise not_found("store", store_name)

    try:
        return request.app.state.records.replay_from_log(store_name)
    except Exception as error:
        log.exception("failed to replay store %s", store_name)
        raise store_down("replay_failed", f"failed to replay store {store_name}: {error}")
