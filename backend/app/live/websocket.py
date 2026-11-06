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

    await websocket.accept()
    log.info("live websocket opened for run %s", run_id)

    try:
        while True:
            raw_message = await asyncio.to_thread(pubsub.get_message, timeout= 0.5)

            if raw_message is not None:
                message_type = raw_message.get("type")

                if message_type == "message":
                    data = raw_message.get("data")
                    await websocket.send_text(data)

                    try:
                        parsed = json.loads(data)
                        msg_type = parsed.get("type")
                        status = parsed.get("status")
                        terminal_statuses = ("done", "failed", "cancelled")
                        if msg_type == "status" and status in terminal_statuses:
                            await asyncio.sleep(0.1)
                            await websocket.close(code = 1000, reason = "run finished")
                            break
                    except (json.JSONDecodeError, AttributeError):
                        pass
    except WebSocketDisconnect:
        log.info("live websocket closed by client for run %s", run_id)
    except Exception:
        log.exception("live websocket error for run %s", run_id)