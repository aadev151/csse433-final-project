from fastapi import APIRouter, Query, Request, Response

from app.errors import conflict, not_found, validation_error
from app.runs.models import STATUS, RunCancel, RunConfig, SignalReport, Progress, Run, RunInput, ReadingPoint, ReadingsResponse, FaultWindow, QueueState, to_run
from app.records.models import WriteInfo, WriteResponse
from app.records.replicated import RecordNotFound, VersionConflict
import datetime

RECORD_TYPE = "run"

router = APIRouter(prefix="/api/runs", tags=["runs"])

def _records(request):
    return request.app.state.records

def _fields_from_input(body):
    return body.model_dump(exclude={"version"})

def _get_or_404(records, run_id):
    record, _ = records.get(RECORD_TYPE, run_id)
    if record is None:
        raise not_found("run", run_id)
    return record

#-----------------------------------------------------------------------------------
# CRUD Operations

@router.post("", response_model=WriteResponse[Run])
def create_run(body: RunInput, request: Request):
    records = _records(request)
    fields = _fields_from_input(body)
    fields["status"] = "queued"
    fields["started_at"] = str(datetime.datetime.now())
    fields["finished_at"] = None
    record, write = records.create(RECORD_TYPE, fields)
    run = to_run(record)
    return WriteResponse[Run](record=run, write=write)

@router.get("/{run_id}", response_model=Run)
def get_run(run_id: str, request: Request, response: Response):
    record, served_by = _records(request).get(RECORD_TYPE, run_id)
    response.headers["X-Served-By"] = served_by
    if record is None:
            raise not_found("run", run_id)

@router.patch("/{run_id}/cancel", response_model=Run)
def cance_run(run_id: str, body: RunCancel, request: Request):
     records = _records(request)
     fields = _fields_from_input(body)
     record, write = records.update(RECORD_TYPE, run_id, fields)
     run = to_run(record)
     return WriteResponse[Run](record = run, write = write)

@router.delete("/{run_id}", response_model=WriteResponse[None])
def delete_run(run_id: str, request: Request):
     records = _records(request)
     _get_or_404(records, run_id)
     try:
        write = records.delete(RECORD_TYPE, run_id)
     except RecordNotFound:
        raise not_found("run", run_id)
     return WriteResponse[None](record=None, write=write)
#-----------------------------------------------------------------------------------



# @router.get("/{run_id}/readings", response_model=list[Run])
# def list_runs(
#     request: Request,
#     response: Response,
#     signal_id: str,
#     symbol: str,
#     from_: str = Query(default = None),
#     to_: str = Query(default = None),
#     max_points: int = Query(default = 2000)
# ):
#     all_records, served_by = _records(request).list(RECORD_TYPE)
#     response.headers["X-Served-By"]
#     runs = [to_run(record) for record in all_records]
#     sorted_runs = sorted(runs, key = lambda run: run.experiment_id)
#     return sorted_runs

# @router.get("/{run_id}", response_model = Run)
# def get_run(run_id: str, request: Request, response: Response):
#     record, served_by = _records(request).get(RECORD_TYPE, run_id)
#     response.headers["X-Served-By"]
#     if record is None:
#         raise not_found("run", run_id)

# @router.post("", response_model = WriteResponse[Run])
# def create_run(body: RunInput, request: Request):
#     records = _records(request)
#     fields = _fields_from_input(body)
#     fields["status"] = "queued"
#     record, write = records.create(RECORD_TYPE, fields)
#     run = to_run(record)
#     return WriteResponse[Run](record = run, write = write)

# @router.put("/{run_id}", response_model = WriteResponse[Run])
# def update_run(run_id: str, body: RunInput, request: Request):
#     records = _records(request)
#     current = _get_or_404(records, run_id)
#     current_status = current.get("status")
#     if current_status == "running":
#         raise conflict("already_running", "Cannot edit an experiment while it is running")
#     fields = _fields_from_input(body)
#     try:
#         record, write = records.update(
#             RECORD_TYPE,
#             run_id,
#             fields,
#             expected_version = body.version,
#         )
#     except RecordNotFound:
#         raise not_found("run", run_id)
#     except VersionConflict as error:
#         raise conflict(
#             "version_conflict",
#             f"This run was changed by someone else (now at version {error.current_version}). "
#             "Reload it and try again",
#         )
#     run = to_run(record)
#     return WriteResponse[Run](record = run, write = write)

# @router.delete("/{run_id}", response_model = WriteResponse[None])
# def delete_run(run_id: str, request: Request):
#     records = _records(request)
#     _get_or_404(records, run_id)
#     try:
#         write = records.delete(RECORD_TYPE, run_id)
#     except RecordNotFound:
#         raise not_found("run", run_id)
#     return WriteResponse[None](record=None, write=write)

# # @router.post("/{run_id}/cancel",response_model = WriteResponse[Run])
# # def cancel_run(run_id:str, request: Request):
    

# @router.get("/{run_id}/export.csv")
# def export_experiment(run_id: str, request: Request):
#     _get_or_404(_records(request), run_id)
#     raise not_found("export", "Run results are not available yet")

