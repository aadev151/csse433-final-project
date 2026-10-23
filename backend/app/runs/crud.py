import math
from typing import Literal, Optional
from app.records.replicated import WriteInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    Field,
    StrictInt,
)

MAX_DELAY_MS = 24 * 60 * 60 * 1000

CONSISTENCY_TYPE = Literal["ONE", "QUORUM", "ALL"]
NODE_OUTAGE = Literal["none", "one_node_down"]
STATUS = Literal["queued", "waiting_for_cassandra", "running", "done", "failed", "cancelled"]
KIND = Literal["delay", "packet_loss", "clock_skew", "node_down"]
CASSANDRA_DOWN = Literal["cassandra_down"]

class RunConfig(BaseModel):
    consistency: CONSISTENCY_TYPE
    delay_ms: StrictInt = Field(ge=0, le=MAX_DELAY_MS)
    packet_loss_pct: StrictInt = Field(ge=0, le=MAX_DELAY_MS)
    clock_skew_ms: StrictInt = Field(ge=0, le=MAX_DELAY_MS)
    node_outage: NODE_OUTAGE

class SignalReport(BaseModel):
    avg_error: int
    max_error: int
    wrong_call_rate: int
    staleness_p50_ms: int
    staleness_p99_ms: int
    latency_p50_ms: int
    latency_p99_ms: int
    readings_count: int

class Progress(BaseModel):
    pct: int
    replayed_until: Optional[str] = None

class Run(BaseModel):
    id: str
    experiment_id: str
    config: RunConfig
    status: STATUS
    queue_position: Optional[int] = None
    progress: Progress
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    report: dict[StrictStr, SignalReport] = Field(default_factory=dict)
    version: int

class ReadingPoint(BaseModel):
    t: str
    value: int
    truth: int
    staleness_ms: int
    latency_ms: int

class ReadingsResponse(BaseModel):
    points: list[ReadingPoint]

class FaultWindow(BaseModel):
    start:str
    end: str
    kind: KIND
    target: str
    value: Optional[int] = None

class QueueState(BaseModel):
    running: Optional[Run] = None
    waiting: list[Run]
    blocked_reason: Optional[CASSANDRA_DOWN] = None