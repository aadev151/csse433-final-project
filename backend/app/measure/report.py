import math


def percentile(values, pct):
    if not values:
        return 0.0

    ordered = sorted(values)
    rank = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return float(ordered[rank])


def _direction(change):
    return (change > 0) - (change < 0)


def _wrong_calls(series):
    wrong = 0
    for prev, cur in zip(series, series[1:]):
        if _direction(cur["value"] - prev["value"]) != _direction(cur["truth"] - prev["truth"]):
            wrong += 1
    return wrong, max(0, len(series) - 1)


def build_report(points, signal_ids):
    report = {}
    for signal_id in signal_ids:
        series = [point for point in points if point["signal_id"] == signal_id]
        scale = (sum(abs(point["truth"]) for point in series) / len(series) if series else 0.0) or 1.0
        errors = [abs(point["value"] - point["truth"]) / scale for point in series]
        by_symbol = {}
        for point in series:
            by_symbol.setdefault(point["symbol"], []).append(point)

        wrong = calls = 0
        for symbol_series in by_symbol.values():
            symbol_series.sort(key=lambda p: p["t_us"])
            w, c = _wrong_calls(symbol_series)
            wrong += w
            calls += c

        staleness = [point["staleness_ms"] for point in series]
        latency = [point["latency_ms"] for point in series]

        report[signal_id] = {
            "avg_error": sum(errors) / len(errors) if errors else 0.0,
            "max_error": max(errors) if errors else 0.0,
            "wrong_call_rate": wrong / calls if calls else 0.0,
            "staleness_p50_ms": percentile(staleness, 50),
            "staleness_p99_ms": percentile(staleness, 99),
            "latency_p50_ms": percentile(latency, 50),
            "latency_p99_ms": percentile(latency, 99),
            "readings_count": len(series),
        }

    return report
