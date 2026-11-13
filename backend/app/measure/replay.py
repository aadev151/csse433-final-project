import threading
import time

from cassandra import ConsistencyLevel


US_PER_HOUR = 3_600_000_000
MAX_IN_FLIGHT = 128

TRADE_INSERT = ("INSERT INTO market.trades (run_id, symbol, hour_bucket, event_us, trade_id, price, qty, buyer_is_maker, ingest_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
QUOTE_INSERT = ("INSERT INTO market.quotes (run_id, symbol, hour_bucket, event_us, update_id, bid_px, bid_qty, ask_px, ask_qty, ingest_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
LATEST_INSERT = ("INSERT INTO market.latest_quote (run_id, symbol, event_us, bid_px, bid_qty, ask_px, ask_qty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)")


def merge_events(trades, quotes):
    return sorted([(t[0], "trade", t) for t in trades] + [(q[0], "quote", q) for q in quotes])


class Replayer:
    def __init__(self, session, run_id, symbol, events, speed, stop=None):
        if not events:
            raise ValueError(f"No events to replay for {symbol}")
        self._session = session
        self.run_id = run_id
        self.symbol = symbol
        self.events = events
        self.speed = speed
        self.stop = stop if stop is not None else threading.Event()
        self.trade = self._prepare(TRADE_INSERT)
        self.quote = self._prepare(QUOTE_INSERT)
        self.latest = self._prepare(LATEST_INSERT)
        self.slots = threading.Semaphore(MAX_IN_FLIGHT)
        self.watermark_us = events[0][0] - 1
        self.failed_writes = 0
        self.first_us = events[0][0]
        self.last_us = events[-1][0]

    def _prepare(self, query):
        statement = self._session.prepare(query)
        statement.consistency_level = ConsistencyLevel.ONE
        return statement

    def _write(self, statement, values):
        self.slots.acquire()
        future = self._session.execute_async(statement, values)
        future.add_callbacks(callback=self._ok, errback=self._failed)

    def _ok(self, _):
        self.slots.release()

    def _failed(self, _):
        self.failed_writes += 1
        self.slots.release()

    def progress(self):
        span = max(1, self.last_us - self.first_us)
        return min(1.0, max(0.0, (self.watermark_us - self.first_us) / span))

    def run(self):
        started = time.monotonic()
        first_us = self.events[0][0]
        for event_us, kind, row in self.events:
            wait = started + (event_us - first_us) / 1_000_000 / self.speed - time.monotonic()
            if wait > 0 and self.stop.wait(wait):
                break
            if self.stop.is_set():
                break

            bucket = event_us // US_PER_HOUR
            ingest_us = time.time_ns() // 1_000
            if kind == "trade":
                _, trade_id, price, qty, buyer_is_maker = row
                self._write(self.trade, (self.run_id, self.symbol, bucket, event_us, trade_id, price, qty, buyer_is_maker, ingest_us))
            else:
                _, update_id, bid, bid_qty, ask, ask_qty = row
                self._write(self.quote, (self.run_id, self.symbol, bucket, event_us, update_id, bid, bid_qty, ask, ask_qty, ingest_us))
                self._write(self.latest, (self.run_id, self.symbol, event_us, bid, bid_qty, ask, ask_qty))
            self.watermark_us = event_us
        
        for _ in range(MAX_IN_FLIGHT):
            self.slots.acquire()
