from fastapi import APIRouter, Request, Response

from app.errors import conflict, not_found, validation_error
from app.records.models import WriteResponse
from app.records.replicated import RecordNotFound, VersionConflict
from app.signals.models import Signal, SignalInput, to_signal

RECORD_TYPE = "signal"

router = APIRouter(prefix="/api/signals", tags=["signals"])

def _records(request):
    return request.app.state.records

def _fields_from_input(body):
    return body.model_dump(exclude={"version"})

def _require_unique_name(records, name, ignore_id=None):
    existing, _ = records.list(RECORD_TYPE)
    for record in existing:
        if record["id"] != ignore_id and record["name"].lower() == name.lower():
            raise validation_error(f'A signal named "{name}" already exists')

def _experiments_using(records, signal_id):
    experiments, _ = records.list("experiment")
    return [
        {"id": experiment["id"], "name": experiment.get("name", "")}
        for experiment in experiments
        if signal_id in experiment.get("signal_ids", [])
    ]

def _get_or_404(records, signal_id):
    record, _ = records.get(RECORD_TYPE, signal_id)
    if record is None:
        raise not_found("signal", signal_id)
    return record

@router.get("", response_model=list[Signal])
def list_signals(request: Request, response: Response):
    records, served_by = _records(request).list(RECORD_TYPE)
    response.headers["X-Served-By"] = served_by
    signals = [to_signal(record) for record in records]
    return sorted(signals, key=lambda signal: (not signal.builtin, signal.name.lower()))

@router.get("/{signal_id}", response_model=Signal)
def get_signal(signal_id: str, request: Request, response: Response):
    record, served_by = _records(request).get(RECORD_TYPE, signal_id)
    response.headers["X-Served-By"] = served_by
    if record is None:
        raise not_found("signal", signal_id)
    return to_signal(record)

@router.post("", response_model=WriteResponse[Signal])
def create_signal(body: SignalInput, request: Request):
    records = _records(request)
    _require_unique_name(records, body.name)
    record, write = records.create(RECORD_TYPE, {**_fields_from_input(body), "builtin": False})
    return WriteResponse[Signal](record=to_signal(record), write=write)

@router.put("/{signal_id}", response_model=WriteResponse[Signal])
def update_signal(signal_id: str, body: SignalInput, request: Request):
    records = _records(request)
    current = _get_or_404(records, signal_id)
    if current.get("builtin"):
        raise conflict("builtin", "Built-in signals cannot be edited")
    _require_unique_name(records, body.name, ignore_id=signal_id)
    try:
        record, write = records.update(
            RECORD_TYPE,
            signal_id,
            _fields_from_input(body),
            expected_version=body.version,
        )
    except RecordNotFound:
        raise not_found("signal", signal_id)
    except VersionConflict as error:
        raise conflict(
            "version_conflict",
            f"This signal was changed by someone else (now at version {error.current_version}). "
            "Reload it and try again.",
        )
    return WriteResponse[Signal](record=to_signal(record), write=write)

@router.delete("/{signal_id}", response_model=WriteResponse[None])
def delete_signal(signal_id: str, request: Request):
    records = _records(request)
    current = _get_or_404(records, signal_id)
    if current.get("builtin"):
        raise conflict("builtin", "Built-in signals cannot be deleted")
    used_by = _experiments_using(records, signal_id)
    if used_by:
        raise conflict(
            "in_use",
            f"This signal is used by {len(used_by)} experiment(s)",
            used_by=used_by,
        )
    try:
        write = records.delete(RECORD_TYPE, signal_id)
    except RecordNotFound:
        raise not_found("signal", signal_id)
    return WriteResponse[None](record=None, write=write)