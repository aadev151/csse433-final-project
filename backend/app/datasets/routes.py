import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Response, Request

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "raw-data"
FILE_PATTERN = re.compile(r"^(?P<symbol>[A-Z]+)-(?P<kind>trades|bookTicker)-(?P<day>\d{4}-\d{2}-\d{2})\.zip$")

KIND_NAMES = {"trades": "trades", "bookTicker": "quotes"}

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


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
