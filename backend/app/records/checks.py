import json

from app.records.models import RECORD_TYPES, STORE_NAMES


def require_str(name, value):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def require_int(name, value, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


def require_choice(name, value, choices):
    require_str(name, value)
    if value not in choices:
        raise ValueError(f"{name} must be one of {list(choices)}, got {value!r}")
    return value


def require_store(value):
    return require_choice("store", value, STORE_NAMES)


def require_record_type(value):
    return require_choice("record_type", value, RECORD_TYPES)


def require_record(record, record_id=None):
    if not isinstance(record, dict):
        raise TypeError(f"record must be a dict, got {type(record).__name__}")
    if "id" not in record or "version" not in record:
        raise ValueError("record must contain id and version")
    require_str("record['id']", record["id"])
    require_int("record['version']", record["version"], minimum=1)
    if record_id is not None and record["id"] != record_id:
        raise ValueError(f"record['id'] {record['id']!r} does not match record_id {record_id!r}")
    try:
        json.dumps(record, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"record must be JSON-serializable: {error}") from error
    return record