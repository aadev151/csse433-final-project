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

@router.put("/{experiment_id}", response_model = WriteResponse[Experiment])
def update_experiment(experiment_id: str, body: ExperimentInput, request: Request):
    records = _records(request)
    current = _get_or_404(records, experiment_id)
    current_status = current.get("status")
    if current_status == "running":
        raise conflict("already_running", "Cannot edit an experiment while it is running")
    _validate_signal_ids(records, body.signal_ids)
    fields = _fields_from_input(body)
    try:
        record, write = records.update(
            RECORD_TYPE,
            experiment_id,
            fields,
            expected_version = body.version,
        )
    except RecordNotFound:
        raise not_found("experiment", experiment_id)
    except VersionConflict as error:
        raise conflict(
            "version_conflict",
            f"This experiment was changed by someone else (now at version {error.current_version}). "
            "Reload it and try again",
        )
    experiment = to_experiment(record)
    return WriteResponse[Experiment](record = experiment, write = write)

@router.delete("/{experiment_id}", response_model = WriteResponse[None])
def delete_experiment(experiment_id: str, request: Request):
    records = _records(request)
    _get_or_404(records, experiment_id)
    all_runs, _ = records.list("run")
    for run in all_runs:
        run_experiment_id = run.get("experiment_id")
        if run_experiment_id == experiment_id:
            try:
                records.delete("run", run["id"])
            except:
                pass
    all_annotations, _ = records.list("annotation")
    for annotation in all_annotations:
        target_type = annotation.get("target_type")
        target_id = annotation.get("target_id")
        if target_type == "experiment" and target_id == experiment_id:
            try:
                records.delete("annotation", annotation["id"])
            except:
                pass
    try:
        write = records.delete(RECORD_TYPE, experiment_id)
    except RecordNotFound:
        raise not_found("experiment", experiment_id)
    return WriteResponse[None](record = None, write = write)

@router.post("/{experiment_id}/clone", response_model = WriteResponse[Experiment])
def clone_experiment(experiment_id: str, request: Request):
    records = _records(request)
    current = _get_or_404(records, experiment_id)
    clone_name = f"{current["name"]} (copy)"
    fields = {
        "name": clone_name,
        "symbols": current["symbols"],
        "dates": current["dates"],
        "signal_ids": current["signal_ids"],
        "params": current["params"],
        "replay_speed": current["replay_speed"],
        "tags": current["tags"],
        "notes": current["notes"],
        "status": "draft",
        "run_count": 0,
    }
    record, write = records.create(RECORD_TYPE, fields)
    experiment = to_experiment(record)
    return WriteResponse[Experiment](record = experiment, write = write)