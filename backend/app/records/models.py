from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel

STORE_NAMES = ("mongodb", "cassandra", "redis")
RECORD_TYPES = ("signal", "experiment", "run", "annotation", "dataset")

StoreName = Literal["mongodb", "cassandra", "redis"]
ServedBy = Literal["mongodb", "cassandra", "redis", "snapshot"]
RecordType = Literal["signal", "experiment", "run", "annotation", "dataset"]


def _in_store_order(names):
    return [name for name in STORE_NAMES if name in names]


class WriteInfo(BaseModel):
    status: Literal["committed", "pending"]
    stores_written: list[StoreName]
    stores_pending: list[StoreName]

    @classmethod
    def from_results(cls, written, pending):
        written = set(written)
        pending = set(pending)
        unknown = (written | pending) - set(STORE_NAMES)
        if unknown:
            raise ValueError(f"unknown store names: {sorted(unknown)}")
        overlap = written & pending
        if overlap:
            raise ValueError(f"stores cannot be both written and pending: {sorted(overlap)}")
        return cls(
            status="committed" if not pending else "pending",
            stores_written=_in_store_order(written),
            stores_pending=_in_store_order(pending),
        )


T = TypeVar("T")


class WriteResponse(BaseModel, Generic[T]):
    record: Optional[T] = None
    write: WriteInfo