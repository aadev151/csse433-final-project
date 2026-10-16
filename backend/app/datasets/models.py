import re
from datetime import date, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

from app.records.models import WriteInfo

Symbol = Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
DatasetKind = Literal["trades", "quotes"]
DatasetStatus = Literal["downloading", "verifying", "ready", "failed"]

MAX_IMPORT_DAYS = 31
DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DatasetImportInput(BaseModel):
    """Body of POST /api/datasets/import. start and end are inclusive YYYY-MM-DD days."""

    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    kind: DatasetKind
    start: StrictStr
    end: StrictStr

    @field_validator("kind")
    @classmethod
    def trades_only_for_now(cls, value):
        if value == "quotes":
            raise ValueError(
                "Quote data isn't available from Binance's spot archive yet; only trades can be imported"
            )
        return value

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

    @model_validator(mode="after")
    def valid_range(self):
        start = self.start_date()
        end = self.end_date()
        if end < start:
            raise ValueError("end must be on or after start")
        if (end - start).days + 1 > MAX_IMPORT_DAYS:
            raise ValueError(f"at most {MAX_IMPORT_DAYS} days can be imported at once")
        return self

    def start_date(self):
        return date.fromisoformat(self.start)

    def end_date(self):
        return date.fromisoformat(self.end)

    def days(self):
        start = self.start_date()
        return [start + timedelta(days=offset) for offset in range((self.end_date() - start).days + 1)]


class Dataset(BaseModel):
    """A dataset as returned by the API (matches the contract's Dataset type)."""

    id: str
    symbol: Symbol
    kind: DatasetKind
    day: str
    status: DatasetStatus
    row_count: Optional[int]
    size_bytes: Optional[int]
    checksum_ok: Optional[bool]
    error: Optional[str]
    created_at: str
    version: int


class DatasetImportResponse(BaseModel):
    records: list[Dataset]
    write: WriteInfo


def to_dataset(record):
    return Dataset(**{field: record[field] for field in Dataset.model_fields})