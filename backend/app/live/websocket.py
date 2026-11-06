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
    pass