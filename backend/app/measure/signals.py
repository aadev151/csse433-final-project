from dataclasses import dataclass


QUOTE_FIELDS = ("mid", "bid_px", "ask_px", "spread")
TRADE_FIELDS = ("price", "qty", "notional")  # notional = price * qty


@dataclass(frozen=True)
class SignalSpec:
    id: str
    kind: str  # quote / last_trade / trade_total
    field: str
    window_us: int


def spec_from_signal(record):
    params = record.get("params", {})
    inputs = record.get("inputs", [])

    if record["type"] == "latest-value" and "quotes" in inputs:
        field = str(params.get("field", "mid"))
        if field not in QUOTE_FIELDS:
            raise ValueError(f"signal {record['id']}: quote field must be one of {QUOTE_FIELDS}, got {field}")
        return SignalSpec(id=record["id"], kind="quote", field=field, window_us=0)

    if record["type"] == "latest-value" and "trades" in inputs:
        field = str(params.get("field", "price"))
        if field not in TRADE_FIELDS:
            raise ValueError(f"signal {record['id']}: trade field must be one of {TRADE_FIELDS}, got {field}")
        return SignalSpec(id=record["id"], kind="last_trade", field=field, window_us=0)

    if record["type"] == "running-total" and "trades" in inputs:
        field = str(params.get("field", "qty"))
        if field not in TRADE_FIELDS:
            raise ValueError(f"signal {record['id']}: trade field must be one of {TRADE_FIELDS}, got {field}")
        window_ms = int(record.get("window_ms", 0))
        if window_ms <= 0:
            raise ValueError(f"signal {record['id']}: running-total window_ms must be > 0, got {window_ms}")
        return SignalSpec(id=record["id"], kind="trade_total", field=field, window_us=window_ms * 1000)

    raise ValueError(f"signal {record['id']}: unsupported type/inputs combination: {record['type']} / {inputs}")


def quote_value(field, bid, ask):
    if field == "mid":
        return (bid + ask) / 2
    if field == "spread":
        return ask - bid
    if field == "bid_px":
        return bid
    if field == "ask_px":
        return ask


def trade_value(field, price, qty):
    if field == "price":
        return price
    if field == "qty":
        return qty
    if field == "notional":
        return price * qty
