import logging
import time

from cassandra import ConsistencyLevel

from app.measure.signals import quote_value, trade_value


log = logging.getLogger(__name__)

US_PER_HOUR = 60 * 60 * 1_000_000
READ_TIMEOUT_S = 2.0

QUERIES = {
    "quote": "SELECT event_us, bid_px, ask_px FROM market.latest_quote WHERE run_id = ? AND symbol = ?",
    "last_trade": "SELECT event_us, price, qty FROM market.trades "
                  "WHERE run_id = ? AND symbol = ? AND hour_bucket = ? ORDER BY event_us DESC LIMIT 1",
    "trade_total": "SELECT event_us, price, qty FROM market.trades "
                   "WHERE run_id = ? AND symbol = ? AND hour_bucket = ? AND event_us > ?",
}


class ScheduleClock:
    def __init__(self, first_event_us, speed):
        self._first_event_us = first_event_us
        self._speed = speed
        self._started = time.monotonic()

    def __call__(self):
        elapsed_s = time.monotonic() - self._started
        return self._first_event_us + int(elapsed_s * 1_000_000 * self._speed)


class Reader:
    def __init__(self, session, run_id, symbol, specs, consistency, truth, clock):
        self._session = session
        self._run_id = run_id
        self._symbol = symbol
        self._specs = specs
        self._truth = truth
        self._clock = clock
        self._statements = {}
        for name, query in QUERIES.items():
            statement = session.prepare(query)
            statement.consistency_level = getattr(ConsistencyLevel, consistency)
            self._statements[name] = statement
        self.failed_reads = 0

    def _query(self, spec, query_us):
        if spec.kind == "quote":
            args = (self._run_id, self._symbol)
            return list(self._session.execute(self._statements["quote"], args, timeout=READ_TIMEOUT_S))

        bucket = query_us // US_PER_HOUR
        if spec.kind == "last_trade":
            for b in (bucket, bucket - 1):
                args = (self._run_id, self._symbol, b)
                rows = list(self._session.execute(self._statements["last_trade"], args, timeout=READ_TIMEOUT_S))
                if rows:
                    return rows
            return []

        if spec.kind == "trade_total":
            since = query_us - spec.window_us
            rows = []
            for b in range(since // US_PER_HOUR, bucket + 1):
                args = (self._run_id, self._symbol, b, since)
                rows.extend(self._session.execute(self._statements["trade_total"], args, timeout=READ_TIMEOUT_S))
            return rows

    def read_once(self, spec):
        query_us = self._clock()
        started = time.perf_counter()
        try:
            rows = self._query(spec, query_us)
        except Exception as e:
            self.failed_reads += 1
            return None

        latency_ms = (time.perf_counter() - started) * 1000
        newest_seen = max((row.event_us for row in rows), default=None)

        truth_us = max(query_us, newest_seen or 0)
        truth = self._truth.evaluate(spec, truth_us)
        if truth is None:
            return None

        truth_value, truth_newest = truth
        if spec.kind == "trade_total":
            window_start_us = truth_us - spec.window_us
            in_window = [row for row in rows if row.event_us > window_start_us]
            value = sum(trade_value(spec.field, row.price, row.qty) for row in in_window)
            read_newest = max((row.event_us for row in in_window), default=window_start_us)
        else:
            if not rows:
                return None
            row = rows[0]
            if spec.kind == "quote":
                value = quote_value(spec.field, row.bid_px, row.ask_px)
            else:
                value = trade_value(spec.field, row.price, row.qty)
            read_newest = row.event_us

        staleness_ms = max(0, (truth_newest or read_newest) - read_newest) / 1000
        return {
            "signal_id": spec.id,
            "symbol": self._symbol,
            "t_us": time.time_ns() // 1000,
            "market_us": truth_us,
            "value": value,
            "truth": truth_value,
            "staleness_ms": staleness_ms,
            "latency_ms": latency_ms,
        }

    def run(self, stop, on_point, interval_s=0.1):
        while not stop.is_set():
            tick = time.perf_counter()
            for spec in self._specs:
                point = self.read_once(spec)
                if point is not None:
                    on_point(point)
            elapsed = time.perf_counter() - tick
            stop.wait(max(0, interval_s - elapsed))
