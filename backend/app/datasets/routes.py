import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Response, Request

from app.datasets.importer import DownloadError, download_and_verify, file_name
from app.datasets.models import DatasetImportInput
from app.errors import ApiError, not_found, validation_error
from app.records.models import STORE_NAMES, WriteInfo
from app.records.replicated import RecordExists, RecordNotFound

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "raw-data"
FILE_PATTERN = re.compile(r"^(?P<symbol>[A-Z]+)-(?P<kind>trades|bookTicker)-(?P<day>\d{4}-\d{2}-\d{2})\.zip$")
# Dataset ids are "{symbol}-{kind}-{day}" (M4 section 5), where kind is the API name (trades / quotes)
DATASET_ID_PATTERN = re.compile(r"^(?P<symbol>[A-Z]+)-(?P<kind>trades|quotes)-(?P<day>\d{4}-\d{2}-\d{2})$")

KIND_NAMES = {"trades": "trades", "bookTicker": "quotes"}

# Same cap as the frontend import form
MAX_IMPORT_DAYS = 31

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _dataset_id(symbol, kind, day):
    return f"{symbol}-{kind}-{day}"


def _days_between(start, end):
    days = []
    day = start
    while day <= end:
        days.append(day.isoformat())
        day += timedelta(days=1)
    return days


def _on_disk(raw_data_dirs, name):
    return any((Path(folder) / name).is_file() for folder in raw_data_dirs)


def _combined_write(writes):
    # One import creates one record per day. If any of them is still waiting on a store,
    # report that store as pending so the UI shows the amber "waiting to sync" toast.
    pending = set()
    for write in writes:
        pending.update(write.stores_pending)
    written = [name for name in STORE_NAMES if name not in pending]
    return WriteInfo.from_results(written, pending)


@router.get("")
def list_datasets(request: Request, response: Response):
    response.headers["X-Served-By"] = "local"
    datasets = {}
    for folder in request.app.state.settings.raw_data_dirs:
        for path in sorted(Path(folder).glob("*.zip")):
            match = FILE_PATTERN.match(path.name)
            if match is None:
                continue

            kind = KIND_NAMES[match["kind"]]
            dataset_id = f"{match['symbol']}-{kind}-{match['day']}"
            if dataset_id in datasets:
                continue

            stat = path.stat()
            datasets[dataset_id] = {
                "id": dataset_id,
                "symbol": match["symbol"],
                "kind": kind,
                "day": match["day"],
                "status": "ready",
                "row_count": None,
                "size_bytes": stat.st_size,
                "checksum_ok": None,
                "error": None,
                "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "version": 1,
            }

    return sorted(datasets.values(), key=lambda d: (d["day"], d["symbol"], d["kind"]), reverse=True)


@router.post("/import")
def import_datasets(body: DatasetImportInput, request: Request):
    if body.end < body.start:
        raise validation_error("End date is before start date.")
    days = _days_between(body.start, body.end)
    if len(days) > MAX_IMPORT_DAYS:
        raise validation_error(f"Import at most {MAX_IMPORT_DAYS} days at a time.")

    settings = request.app.state.settings
    records = request.app.state.records

    # A day counts as imported when its file is already in any raw-data folder,
    # because that is what replay and GET /api/datasets look at.
    new_days = [
        day for day in days
        if not _on_disk(settings.raw_data_dirs, file_name(body.symbol, body.kind, day))
    ]
    if not new_days:
        raise validation_error("All of those days are already imported.")

    # New files always go into the first raw-data folder
    folder = settings.raw_data_dirs[0]
    created = []
    writes = []
    failed = []
    for day in new_days:
        # Download -> verify first. If that fails nothing is saved and no record is made,
        # so the same day can simply be imported again later.
        try:
            size_bytes = download_and_verify(folder, body.symbol, body.kind, day)
        except DownloadError as error:
            failed.append({"day": day, "error": str(error)})
            continue

        # The file is verified at this point, so the record is created once with its final
        # status and never needs a later status update.
        fields = {
            "symbol": body.symbol,
            "kind": body.kind,
            "day": day,
            "status": "ready",
            "row_count": None,
            "size_bytes": size_bytes,
            "checksum_ok": True,
            "error": None,
        }
        try:
            record, write = records.create("dataset", fields, record_id=_dataset_id(body.symbol, body.kind, day))
        except RecordExists:
            # An old record with this id is still around (DELETE does not remove records yet,
            # see the TODO there). The verified file is back on disk, so it is imported again.
            continue
        created.append(record)
        writes.append(write)

    if not created and failed:
        # Nothing was saved anywhere, so report it as a failed request (502 = Binance side)
        message = "; ".join(f"{item['day']}: {item['error']}" for item in failed)
        raise ApiError(502, "download_failed", f"Could not import any of those days. {message}")
    if not created:
        raise validation_error("All of those days are already imported.")

    # "failed" lists days that could not be downloaded or verified when others worked
    return {"records": created, "failed": failed, "write": _combined_write(writes)}


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, request: Request):
    match = DATASET_ID_PATTERN.match(dataset_id)
    if match is None:
        raise not_found("dataset", dataset_id)

    name = file_name(match["symbol"], match["kind"], match["day"])
    removed = False
    # Remove it from every raw-data folder, otherwise GET would still list the other copy
    for folder in request.app.state.settings.raw_data_dirs:
        path = Path(folder) / name
        if path.is_file():
            path.unlink()
            removed = True
        checksum_path = Path(folder) / (name + ".CHECKSUM")
        if checksum_path.is_file():
            checksum_path.unlink()

    if not removed:
        raise not_found("dataset", dataset_id)

    write = WriteInfo.from_results([], [])
    try:
        write = request.app.state.records.delete("dataset", dataset_id)
    except RecordNotFound:
        pass

    return {"record": None, "write": write}
