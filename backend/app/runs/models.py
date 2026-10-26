import re
from typing import Literal, Optional
from app.records.replicated import WriteInfo
from pydantic import BaseModel, Field, StrictInt, ConfigDict

from app.records.models import WriteInfo

CONSISTENCY_TYPE = Literal["ONE", "QUORUM", "ALL"]
NODE_OUTAGE = Literal["none", "one_node_down"]
STATUS = Literal["queued", "waiting_for_cassandra", "running", "done", "failed", "cancelled"]
KIND = Literal["delay", "packet_loss", "clock_skew", "node_down"]
CASSANDRA_DOWN = Literal["cassandra_down"]

class RunConfig(BaseModel):
    consistency: CONSISTENCY_TYPE
    delay_ms: StrictInt = Field(ge=0)
    packet_loss_pct: StrictInt = Field(ge=0, le=100)
    clock_skew_ms: StrictInt
    node_outage: NODE_OUTAGE

class SignalReport(BaseModel):
    avg_error: float
    max_error: float
    wrong_call_rate: float
    staleness_p50_ms: float
    staleness_p99_ms: float
    latency_p50_ms: float
    latency_p99_ms: float
    readings_count: int

class Progress(BaseModel):
    pct: float
    replayed_until: Optional[str] = None

class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    config: RunConfig
    queue_position: Optional[int] = None
    progress: Progress
    error: Optional[str] = None
    report: Optional[dict[str, SignalReport]] = None
    version: int

class RunCancel(BaseModel):
    status: STATUS

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
    report: Optional[dict[str, SignalReport]] = None
    version: int

class ReadingPoint(BaseModel):
    t: str
    value: float
    truth: float
    staleness_ms: float
    latency_ms: float

class ReadingsResponse(BaseModel):
    points: list[ReadingPoint]

class FaultWindow(BaseModel):
    start: str
    end: str
    kind: KIND
    target: str
    value: Optional[float] = None

class QueueState(BaseModel):
    running: Optional[Run] = None
    waiting: list[Run]
    blocked_reason: Optional[CASSANDRA_DOWN] = None


def to_run(record):
    return Run(**{field: record[field] for field in Run.model_fields})