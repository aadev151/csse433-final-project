import csv
import heapq
import io
import threading
import time
import zipfile
from datetime import datetime, timezone

from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster


HOSTS = ["137.112.104.145", "137.112.104.212", "137.112.104.214"]
US_PER_HOUR = 3600_000_000
TRADE_EVENT = 0
QUOTE_EVENT = 1
LAG_WARNING_MS = 1000

INSERTS = {
    "trade": "INSERT INTO market.trades (run_id, symbol, hour_bucket, event_us, trade_id, price, qty, "
             "buyer_is_maker, ingest_us) VALUES (?,?,?,?,?,?,?,?,?)",
    "quote": "INSERT INTO market.quotes (run_id, symbol, hour_bucket, event_us, update_id, bid_px, bid_qty, "
             "ask_px, ask_qty, ingest_us) VALUES (?,?,?,?,?,?,?,?,?,?)",
    "latest": "INSERT INTO market.latest_quote (run_id, symbol, event_us, bid_px, bid_qty, ask_px, ask_qty) "
              "VALUES (?,?,?,?,?,?,?)",
}

def read_csv_rows_from_zip(zip_path):
    with zipfile.ZipFile(zip_path) as zf, zf.open(zf.namelist()[0]) as csv_file:
        for row in csv.reader(io.TextIOWrapper(csv_file, encoding='utf-8')):
            if row[0].isdigit():
                yield row


def to_microseconds(raw_timestamp):
    timestamp = int(raw_timestamp)
    return timestamp * 1000 if timestamp < 10 ** 15 else timestamp


def read_trades(trades_zip):
    # 0 id, 1 price, 2 qty, 3 quote_qty, 4 time, 5 is_buyer_maker
    for row in read_csv_rows_from_zip(trades_zip):
        yield (to_microseconds(row[4]), TRADE_EVENT, int(row[0]), float(row[1]), float(row[2]), row[5] == "true")


def read_quotes(quotes_zip):
    # 0 update_id, 1 best_bid_price, 2 best_bid_qty, 3 best_ask_price, 4 best_ask_qty, 5 transaction_time, 6 event_time
    for row in read_csv_rows_from_zip(quotes_zip):
        yield (to_microseconds(row[5]), QUOTE_EVENT, int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]))


def merge_events_in_time_order(trades_zip, quotes_zip):
    # order by time
    return heapq.merge(read_trades(trades_zip), read_quotes(quotes_zip))


def replay_events(session, run_id, symbol, events, window_start_us, window_end_us, speed, consistency="ONE", max_writes_in_flight=128):
    prepared_inserts = {name: session.prepare(query) for name, query in INSERTS.items()}
    for statement in prepared_inserts.values():
        statement.consistency_level = getattr(ConsistencyLevel, consistency)

    write_slots = threading.BoundedSemaphore(max_writes_in_flight)
    write_stats = {"ok": 0, "failed": 0, "first_error": None}

    def on_write_success(_):
        write_stats["ok"] += 1
        write_slots.release()

    def on_write_failure(error):
        write_stats["failed"] += 1
        write_stats["first_error"] = write_stats["first_error"] or repr(error)
        write_slots.release()

    def write_async(insert_name, values):
        write_slots.acquire()
        session.execute_async(prepared_inserts[insert_name], values).add_callbacks(on_write_success, on_write_failure)

    replay_started_at = time.monotonic()
    first_event_us = None
    max_lag_ms = 0.0
    last_progress_print = 0.0

    try:
        for event in events:
            event_us = event[0]  # when it happened
            if event_us < window_start_us:
                continue
            if event_us >= window_end_us:
                break

            if first_event_us is None:
                first_event_us = event_us

            if speed > 0:
                seconds_until_due = (replay_started_at + (event_us - first_event_us) / 1_000_000 / speed) - time.monotonic()
                if seconds_until_due > 0:
                    time.sleep(seconds_until_due)

                max_lag_ms = max(max_lag_ms, -seconds_until_due * 1000)

            ingest_us = time.time_ns() // 1000
            hour_bucket = event_us // US_PER_HOUR
            if event[1] == TRADE_EVENT:
                write_async("trade", (run_id, symbol, hour_bucket, event_us, event[2], event[3], event[4], event[5], ingest_us))
            else:
                write_async("quote", (run_id, symbol, hour_bucket, event_us, event[2], event[3], event[4], event[5], event[6], ingest_us))
                write_async("latest", (run_id, symbol, event_us, event[3], event[4], event[5], event[6]))

            if time.monotonic() - last_progress_print >= 1:
                last_progress_print = time.monotonic()
                percent_complete = (event_us - window_start_us) / (window_end_us - window_start_us) * 100
                behind = "  BEHIND SCHEDULE" if max_lag_ms > LAG_WARNING_MS else ""
                print(f"Progress: {percent_complete:.2f}%{behind} (max lag {max_lag_ms:.2f} ms, writes ok {write_stats['ok']}, failed {write_stats['failed']})")
    
    except KeyboardInterrupt:
        print("Stopping, waiting for in-flight writes")

    for _ in range(max_writes_in_flight):
        write_slots.acquire()

    elapsed_seconds = time.monotonic() - replay_started_at
    return {
        **write_stats,
        "elapsed_seconds": elapsed_seconds,
        "writes_per_second": write_stats["ok"] / elapsed_seconds if elapsed_seconds > 0 else 0,
        "max_lag_ms": max_lag_ms,
    }


def main():
    run_id = "test1"
    symbol = "BTCUSDT"
    trades_zip = "data/binance/testing/BTCUSDT-trades-2024-03-10.zip"
    quotes_zip = "data/binance/testing/BTCUSDT-bookTicker-2024-03-10.zip"
    window_start = datetime(2024, 3, 10, 0, 0, tzinfo=timezone.utc)
    hours = 0.05
    speed = 10

    window_start_us = int(window_start.timestamp() * 1_000_000)
    window_end_us = window_start_us + int(hours * US_PER_HOUR)

    cluster = Cluster(HOSTS)
    session = cluster.connect()
    events = merge_events_in_time_order(trades_zip, quotes_zip)
    print(replay_events(session, run_id, symbol, events, window_start_us, window_end_us, speed))
    cluster.shutdown()


if __name__ == "__main__":
    main()
