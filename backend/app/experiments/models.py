import re
from typing import Literal, Optional
from app.records.replicated import WriteInfo
from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

CONSISTENCY_TYPE = Literal["ONE", "QUORUM", "ALL"]
NODE_OUTAGE = Literal["none", "one_node_down"]
SYMBOLS = Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
STATUS = Literal["draft", "queued", "running", "done", "failed"]
REPLAY_SPEEDS = (1, 5, 10, 50)

DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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

     @field_validator("start", "end")
     @classmethod
     def valid_day(cls, value):
        if not DAY_PATTERN.match(value):
            raise ValueError("must be a day in YYYY-MM-DD format")
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"is not a real date: {error}") from error
        return value

     @model_validator(mode = "after")
     def end_not_before_start(self):
         start = date.fromisoformat(self.start)
         end = date.fromisoformat(self.end)
         if end < start:
             raise ValueError("end must be on or after start")
         return self

class ExperimentInput(BaseModel):

     model_config = ConfigDict(extra="forbid")

     name: StrictStr = Field(min_length=1)
     symbols: list[SYMBOLS] = Field(min_length=1)
     dates: DateRange
     signal_ids: list[StrictStr] = Field(min_length=1)
     params: ExperimentParams
     replay_speed: StrictInt
     tags: list[StrictStr] = Field(default_factory=list)
     notes: StrictStr = Field(default="")
     version: Optional[StrictInt] = Field(default=None, ge=1)

     @field_validator("name")
     @classmethod
     def name_not_blank(cls, value):
         value = value.strip()
         if not value:
             raise ValueError("Name can not be blank")
         return value

     @field_validator("replay_speed")
     @classmethod
     def valid_replay_speed(cls, value):
         if value not in REPLAY_SPEEDS:
             raise ValueError(f"replay_speed must be one of {list(REPLAY_SPEEDS)}")
         return value

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