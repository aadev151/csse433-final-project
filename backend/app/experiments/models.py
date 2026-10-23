import math
from typing import Literal, Optional
from app.records.replicated import WriteInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr
)

CONSISTENCY_TYPE = Literal["ONE", "QUORUM", "ALL"]
NODE_OUTAGE = Literal["none", "one_node_down"]
SYMBOLS = Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
STATUS = Literal["draft", "queued", "running", "done", "failed"]
REPLAY_SPEEDS = (1, 5, 10, 50)

class ExperimentParams(BaseModel):

     model_config = ConfigDict(extra="forbid")

     consistency: list[CONSISTENCY_TYPE] = Field(min_length=1)
     delay_ms: list[StrictInt] = Field(min_length=1)
     packet_loss_pct: list[StrictInt] = Field(min_length=1)
     clock_skew_ms: list[StrictInt] = Field(min_length=1)
     node_outage: list[NODE_OUTAGE] = Field(min_length=1)

class DateRange(BaseModel):

     model_config = ConfigDict(extra="forbid")

     start: StrictStr
     end: StrictStr

class ExperimentInput(BaseModel):

     model_config = ConfigDict(extra="forbid")

     name: StrictStr = Field(min_length=1)
     symbols: list[SYMBOLS] = Field(min_length=1)
     dates: DateRange
     signal_ids: list[StrictStr] = Field(min_length=1)
     params: ExperimentParams
     replay_speed: StrictInt
     tags: list[StrictStr] = Field(default_factory=list)
     notes: StrictStr = Field(default="", min_length=1)
     version: Optional[StrictInt] = Field(default=None, ge=1)

class Experiment(BaseModel):

     id: str
     name: str
     symbols: list[SYMBOLS]
     dates: DateRange
     signal_ids: list[str]
     params: ExperimentParams
     replay_speed: int
     status: STATUS
     tags: list[str]
     notes: str
     run_count: int
     version: int
     created_at: str
     updated_at: str

class LaunchResponse(BaseModel):
     run_ids: list[str]
     write: WriteInfo

def to_experiment(record):
    return Experiment(**{field: record[field] for field in Experiment.model_fields})