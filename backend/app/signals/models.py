import math
from typing import Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

SignalType = Literal["latest-value", "running-total"]
SignalInputKind = Literal["trades", "quotes"]
ParamValue = Union[StrictInt, StrictFloat, StrictStr]

MAX_WINDOW_MS = 24 * 60 * 60 * 1000
MAX_PARAMS = 20
MAX_PARAM_KEY_LENGTH = 32
MAX_PARAM_STRING_LENGTH = 64


class SignalInput(BaseModel):
    """Body of POST /api/signals and PUT /api/signals/{id}."""

    model_config = ConfigDict(extra="forbid")

    name: StrictStr = Field(min_length=1, max_length=64)
    type: SignalType
    inputs: list[SignalInputKind] = Field(min_length=1)
    window_ms: StrictInt = Field(ge=0, le=MAX_WINDOW_MS)
    params: dict[StrictStr, ParamValue] = Field(default_factory=dict)
    description: StrictStr = Field(default="", max_length=500)
    version: Optional[StrictInt] = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("inputs")
    @classmethod
    def inputs_unique(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("inputs must not repeat")
        return value

    @field_validator("params")
    @classmethod
    def params_are_reasonable(cls, value):
        if len(value) > MAX_PARAMS:
            raise ValueError(f"at most {MAX_PARAMS} params are allowed")
        for key, item in value.items():
            if not key.strip() or len(key) > MAX_PARAM_KEY_LENGTH:
                raise ValueError(f"param names must be 1 to {MAX_PARAM_KEY_LENGTH} characters")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError(f"param {key!r} must be a finite number")
            if isinstance(item, str) and len(item) > MAX_PARAM_STRING_LENGTH:
                raise ValueError(f"param {key!r} must be at most {MAX_PARAM_STRING_LENGTH} characters")
        return value

    @model_validator(mode="after")
    def window_fits_type(self):
        if self.type == "running-total" and self.window_ms == 0:
            raise ValueError("a running-total signal needs window_ms greater than 0")
        return self


class Signal(BaseModel):
    """A signal as returned by the API (matches the contract's Signal type)."""

    id: str
    name: str
    type: SignalType
    inputs: list[SignalInputKind]
    window_ms: int
    params: dict[str, Union[int, float, str]]
    description: str
    builtin: bool
    version: int
    updated_at: str


def to_signal(record):
    return Signal(**{field: record[field] for field in Signal.model_fields})