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

@router.get("", response_model=list[Experiment])
def list_experiments(
    request: Request,
    response: Response,
    status: str = Query(default = None),
    tag: str = Query(default = None),
    q: str = Query(default = None),
):
    all_records, served_by = _records(request).list(RECORD_TYPE)
    response.headers["X-Served-By"] = served_by
    experiments = [to_experiment(record) for record in all_records]
    if status is not None:
        experiments = [exp for exp in experiments if exp.status == status]
    if tag is not None:
        tag_lower = tag.lower()
        experiments = [exp for exp in experiments if any(t.lower() == tag_lower for t in exp.tags)]
    if q is not None:
        q_lower = q.lower()
        experiments = [exp for exp in experiments if q_lower in exp.name.lower()]
    sorted_experiments = sorted(experiments, key = lambda exp: exp.name.lower())
    return sorted_experiments

@router.get("/{experiment_id}", response_model = Experiment)
def get_experiment(experiment_id: str, request: Request, response: Response):
    record, served_by = _records(request).get(RECORD_TYPE, experiment_id)
    response.headers["X-Served-By"] = served_by
    if record is None:
        raise not_found("experiment", experiment_id)
    return to_experiment(record)

@router.post("", response_model = WriteResponse[Experiment])
def create_experiment(body: ExperimentInput, request: Request):
    records = _records(request)
    _validate_signal_ids(records, body.signal_ids)
    fields = _fields_from_input(body)
    fields["status"] = "draft"
    fields["run_count"] = 0
    record, write = records.create(RECORD_TYPE, fields)
    experiment = to_experiment(record)
    return WriteResponse[Experiment](record = experiment, write = write)