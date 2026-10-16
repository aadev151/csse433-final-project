from app.records.replicated import RecordExists

# params are placeholders until the team agrees on what each signal type needs.
BUILTIN_SIGNALS = [
    {
        "id": "builtin-last-price",
        "fields": {
            "name": "Last trade price",
            "type": "latest-value",
            "inputs": ["trades"],
            "window_ms": 0,
            "params": {"field": "price"},
            "description": "Price of the most recent trade.",
            "builtin": True,
        },
    },
    {
        "id": "builtin-volume-5s",
        "fields": {
            "name": "Trade volume (5s)",
            "type": "running-total",
            "inputs": ["trades"],
            "window_ms": 5000,
            "params": {"field": "qty", "side": "both"},
            "description": "Total traded quantity over the last 5 seconds.",
            "builtin": True,
        },
    },
]


def ensure_builtin_signals(records):
    """Create any built-in signal that does not exist yet. Safe to call on every startup."""
    for builtin in BUILTIN_SIGNALS:
        existing, _ = records.get("signal", builtin["id"])
        if existing is not None:
            continue
        try:
            records.create("signal", builtin["fields"], record_id=builtin["id"])
        except RecordExists:
            pass