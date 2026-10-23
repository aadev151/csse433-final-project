from fastapi import APIRouter, Query, Request, Response

from app.errors import conflict, not_found, validation_error
from app.experiments.models import Experiment, ExperimentInput, LaunchResponse, to_experiment
from app.records.models import WriteInfo, WriteResponse
from app.records.replicated import RecordNotFound, VersionConflict

RECORD_TYPE = "experiment"

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

def _records(request):
    return request.app.state.records

def _fields_from_input(body):
    fields = body.model_dump(exclude = {"version"})
    fields["dates"] = {
        "start": body.dates.start,
        "end": body.dates.end,
        }
    fields["params"] = body.params.model_dump()
    return fields

def _get_or_404(records, experiemnt_id):
    record, _ = records.get(RECORD_TYPE, experiemnt_id)
    if record is None:
        raise not_found("experiment", experiemnt_id)
    return record

def _validate_signal_ids(records, signal_ids):
    missing = []
    for signal_id in signal_ids:
        signal, _ = records.get("signal", signal_id)
        if signal is None:
            missing.append(signal_id)
    if missing:
        raise validation_error(f"These signal IDs do not exist: {', '.join(missing)}")