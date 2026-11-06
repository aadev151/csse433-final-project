import asyncio
import json
import logging

import redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

log = logging.getLogger(__name__)

UNAVAILABLE_ERRORS = (RedisConnectionError, RedisTimeoutError)

router = APIRouter()

@router.websocket("/ws/runs/{run_id}/live")
async def run_live(websocket: WebSocket, run_id: str):
    app = websocket.app
    records = app.state.records
    redis_url = app.state.redis_url
    run = records.get("run", run_id)

    if run is None:
        await websocket.close(code = 4004, reason = "run not found")
        return

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_response = True,
            socket_timeout = 2,
            socket_connect_timeout = 2,
        )
        pubsub = client.pubsub(ignore_subscribe_messages = True)
        channel_name = f"run:{run_id}"
        pubsub.subscribe(channel_name)
    except UNAVAILABLE_ERRORS:
        await websocket.close(code = 4003, reason = "redis unavailable")
        return