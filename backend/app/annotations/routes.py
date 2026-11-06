from fastapi import APIRouter, Request, Response

from app.annotations.crud import TARGET_TYPE, Annotation, AnnotationInput, AnnotationUpdate, to_annotation
from app.errors import conflict, not_found, validation_error, store_down
from app.records.models import WriteResponse
from app.records.replicated import RecordNotFound, VersionConflict


RECORD_TYPE = "annotation"

router = APIRouter(prefix="/api/annotations", tags=["annotations"])

def _records(request):
    return request.app.state.records


def _fields_from_input(body):
    return body.model_dump(exclude={"version"})


def _require_target(records, target_type, target_id):
    target, _ = records.get(target_type, target_id)
    if target is None:
        raise validation_error(f"target {target_type}:{target_id} not found")


@router.get("", response_model=list[Annotation])
def list_annotations(target_type: TARGET_TYPE, target_id: str, request: Request, response: Response):
    records, served_by = _records(request).list(RECORD_TYPE)
    response.headers["X-Served-By"] = served_by
    annotations = [
        to_annotation(record)
        for record in records
        if record["target_type"] == target_type and record["target_id"] == target_id
    ]
    return sorted(annotations, key=lambda annotation: annotation.created_at, reverse=True)


@router.post("", response_model=WriteResponse[Annotation])
def create_annotation(body: AnnotationInput, request: Request):
    records = _records(request)
    _require_target(records, body.target_type, body.target_id)
    record, write = records.create(RECORD_TYPE, _fields_from_input(body))
    return WriteResponse[Annotation](record=to_annotation(record), write=write)


@router.put("/{annotation_id}", response_model=WriteResponse[Annotation])
def update_annotation(annotation_id: str, body: AnnotationUpdate, request: Request):
    records = _records(request)
    try:
        record, write = records.update(RECORD_TYPE, annotation_id, _fields_from_input(body), expected_version=body.version)
    except RecordNotFound:
        raise not_found("annotation", annotation_id)
    except VersionConflict as e:
        raise conflict(
            "version_conflict",
            f"This annotation was changed by someone else (now at version {e.current_version}). "
            "Reload it and try again.",
        )
    return WriteResponse[Annotation](record=to_annotation(record), write=write)


@router.delete("/{annotation_id}", response_model=WriteResponse[None])
def delete_annotation(annotation_id: str, request: Request):
    records = _records(request)
    try:
        write = records.delete(RECORD_TYPE, annotation_id)
    except RecordNotFound:
        raise not_found("annotation", annotation_id)
    return WriteResponse[None](record=None, write=write)
