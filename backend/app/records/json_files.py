import json
import logging
import os
import time

log = logging.getLogger(__name__)


def write_json_atomic(path, data):
    """Write data to path so the file is never left half-written."""
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w") as file:
        json.dump(data, file, allow_nan=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp_path, path)


def read_json_or_set_aside(path, validate):
    """Return the parsed file, or None if it does not exist.

    If the file is unreadable or validate() rejects it, the file is moved
    aside as <name>.corrupt-<timestamp> and None is returned.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        validate(data)
        return data
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        corrupt_path = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        path.replace(corrupt_path)
        log.warning("%s was unreadable (%s); moved to %s", path.name, error, corrupt_path)
        return None