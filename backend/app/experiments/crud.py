import math
from typing import Literal, Optional
from app.records.replicated import WriteInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)

MAX_DELAY_MS = 24 * 60 * 60 * 1000

CONSISTENCY_TYPE = Literal["ONE", "QUORUM", "ALL"]
NODE_OUTAGE = Literal["none", "one_node_down"]
SYMBOLS = Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
STATUS = Literal["draft", "queued", "running", "done", "failed"]

class ExperimentParams(BaseModel):

     model_config = ConfigDict(extra="forbid")

     consistency: CONSISTENCY_TYPE
     delay_ms: StrictInt = Field(ge=0, le=MAX_DELAY_MS)
     packet_loss_pct: StrictInt = Field(ge=0, le=MAX_DELAY_MS)
     clock_skew_ms: StrictInt = Field(ge=0, le=MAX_DELAY_MS)
     node_outage: NODE_OUTAGE

class ExperimentInput(BaseModel):
     name: str
     symbols: SYMBOLS
     start_date: str
     end_date: str
     signal_ids: list[str]
     params: ExperimentParams
     replay_speed: int
     tags: list[str]
     notes: str
     version: int

class Experiment(BaseModel):
     id: str
     name: str
     symbols: SYMBOLS
     start_date: str
     end_date: str
     signal_ids: list[str]
     params: ExperimentParams
     replay_speed: int
     status: STATUS
     notes: str
     run_count: int
     version: int
     created_at: str
     updated_at: str

class LaunchResponse(BaseModel):
     run_ids: list[str]
     write: WriteInfo
