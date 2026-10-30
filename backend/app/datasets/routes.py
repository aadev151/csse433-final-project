import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Response

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "raw-data"
FILE_PATTERN = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<kind>trades|quotes)-(?P<day>\d{4}-\d{2}-\d{2})\.zip$")

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("")
def list_datasets(response: Response):
    response.headers["X-Served-By"] = "mongodb"
    datasets = []
    for path in sorted(RAW_DATA_DIR.glob("*.zip")):
        match = FILE_PATTERN.match(path.name)
        if match is None:
            continue
        symbol = f"{match['prefix']}T"
        kind = match["kind"]
        day = match["day"]
        stat = path.stat()
        datasets.append({
            "id": f"{symbol}-{kind}-{day}",
            "symbol": symbol,
            "kind": kind,
            "day": day,
            "status": "ready",
            "row_count": None,
            "size_bytes": stat.st_size,
            "checksum_ok": None,
            "error": None,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "version": 1,
        })
    return datasets
