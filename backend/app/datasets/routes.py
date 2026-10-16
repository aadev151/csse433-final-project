from fastapi import APIRouter, Request, Response

from app.datasets.importer import ImportRequestInvalid
from app.datasets.models import Dataset, DatasetImportInput, DatasetImportResponse, to_dataset
from app.errors import not_found, validation_error
from app.records.models import STORE_NAMES, WriteInfo, WriteResponse
from app.records.replicated import RecordNotFound

RECORD_TYPE = "dataset"

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def combine_writes(writes):
    """One WriteInfo for several writes: a store is pending if any write missed it."""
    if not writes:
        return WriteInfo.from_results(STORE_NAMES, [])
    pending = set()
    for write in writes:
        pending.update(write.stores_pending)
    written = [name for name in STORE_NAMES if name not in pending]
    return WriteInfo.from_results(written, pending)


@router.get("", response_model=list[Dataset])
def list_datasets(request: Request, response: Response):
    records, served_by = request.app.state.records.list(RECORD_TYPE)
    response.headers["X-Served-By"] = served_by
    datasets = [to_dataset(record) for record in records]
    return sorted(datasets, key=lambda dataset: (dataset.day, dataset.symbol, dataset.kind), reverse=True)


@router.post("/import", response_model=DatasetImportResponse)
def import_datasets(body: DatasetImportInput, request: Request):
    importer = request.app.state.importer
    try:
        records, writes = importer.start_import(body.symbol, body.kind, body.days())
    except ImportRequestInvalid as error:
        raise validation_error(str(error))
    return DatasetImportResponse(
        records=[to_dataset(record) for record in records],
        write=combine_writes(writes),
    )


@router.delete("/{dataset_id}", response_model=WriteResponse[None])
def delete_dataset(dataset_id: str, request: Request):
    try:
        write = request.app.state.importer.delete(dataset_id)
    except RecordNotFound:
        raise not_found("dataset", dataset_id)
    return WriteResponse[None](record=None, write=write)