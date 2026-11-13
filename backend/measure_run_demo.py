import argparse
import threading
import time
from datetime import datetime, timezone

from cassandra import ConsistencyLevel
from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile
from cassandra.policies import RoundRobinPolicy

from app.config import load_settings
from app.main import build_records
from app.measure.raw import read_quotes, read_trades
from app.measure.reader import Reader
from app.measure.report import build_report
from app.measure.signals import spec_from_signal
from app.measure.store import ReadingsFile, load_to_cassandra
from app.measure.truth import TruthBook

US_PER_HOUR = 3_600_000_000
MAX_IN_FLIGHT = 128

TRADE_INSERT = ("INSERT INTO market.trades (run_id, symbol, hour_bucket, event_us, trade_id, price, qty, buyer_is_maker) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
QUOTE_INSERT = ("INSERT INTO market.quotes (run_id, symbol, hour_bucket, event_us, update_id, bid_px, bid_qty, ask_px, ask_qty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
LATEST_INSERT = ("INSERT INTO market.latest_quote (run_id, symbol, event_us, bid_px, bid_qty, ask_px, ask_qty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)")


def iso(us):
    return datetime.fromtimestamp(us / 1_000_000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def now_iso():
    return iso(time.time_ns() // 1000)


class Replayer:
    def __init__(self, session, run_id, symbol, events, speed):
        self._session = session
        self.run_id = run_id
        self.symbol = symbol
        self.events = events
        self.speed = speed
        self.trade = self._prepare(TRADE_INSERT)
        self.quote = self._prepare(QUOTE_INSERT)
        self.latest = self._prepare(LATEST_INSERT)
        self.slots = threading.Semaphore(MAX_IN_FLIGHT)
        self.watermark_us = events[0][0] - 1
        self.failed_writes = 0

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

    def run(self):
        started = time.monotonic()
        first_us = self.events[0][0]
        for event_us, kind, row in self.events:
            wait = started + (event_us - first_us) / 1_000_000 / self.speed - time.monotonic()
            if wait > 0:
                time.sleep(wait)

            bucket = event_us // US_PER_HOUR
            if kind == "trade":
                _, trade_id, price, qty, buyer_is_maker = row
                self._write(self.trade, (self.run_id, self.symbol, bucket, event_us, trade_id, price, qty, buyer_is_maker))
            else:
                _, update_id, bid, bid_qty, ask, ask_qty = row
                self._write(self.quote, (self.run_id, self.symbol, bucket, event_us, update_id, bid, bid_qty, ask, ask_qty))
                self._write(self.latest, (self.run_id, self.symbol, event_us, bid, bid_qty, ask, ask_qty))
            self.watermark_us = event_us
        
        for _ in range(MAX_IN_FLIGHT):
            self.slots.acquire()


def parse_args():
    parser = argparse.ArgumentParser(description="Replay + measure one run (features 8 and 9)")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--consistency", choices=["ONE", "QUORUM", "ALL"], required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--trades", default="data/binance/testing/BTCUSDT-trades-2024-03-10.zip")
    parser.add_argument("--quotes", default="data/binance/testing/BTCUSDT-bookTicker-2024-03-10.zip")
    parser.add_argument("--start", default="2024-03-10T00:00:00Z")
    parser.add_argument("--minutes", type=float, default=0.25)
    parser.add_argument("--speed", type=float, default=1)
    parser.add_argument("--delay-ms", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    settings = load_settings()
    records = build_records(settings)

    experiment, _ = records.get("experiment", args.experiment_id)
    if experiment is None:
        raise SystemExit(f"experiment {args.experiment_id} not found in the database")

    specs = [spec_from_signal(records.get("signal", signal_id)[0]) for signal_id in experiment["signal_ids"]]

    start_us = int(datetime.fromisoformat(args.start.replace("Z", "+00:00")).timestamp() * 1_000_000)
    end_us = start_us + int(args.minutes * 60 * 1_000_000)

    print("Loading row data...")
    trades = read_trades(args.trades, start_us, end_us)
    quotes = read_quotes(args.quotes, start_us, end_us)
    print(f"    Loaded {len(trades)} trades and {len(quotes)} quotes")

    events = sorted([(t[0], "trade", t) for t in trades] + [(q[0], "quote", q) for q in quotes])
    truth = TruthBook(trades, quotes)

    profile = ExecutionProfile(load_balancing_policy=RoundRobinPolicy(), request_timeout=5)
    cluster = Cluster(list(settings.cassandra_hosts), execution_profiles={EXEC_PROFILE_DEFAULT: profile}, port=settings.cassandra_port, protocol_version=5, connect_timeout=10)
    session = cluster.connect()

    run, _ = records.create("run", {
        "experiment_id": args.experiment_id,
        "config": {
            "consistency": args.consistency,
            "delay_ms": args.delay_ms,
            "packet_loss_pct": 0,
            "clock_skew_ms": 0,
            "node_outage": "none",
        },
        "status": "running",
        "queue_position": None,
        "progress": {"pct": 0, "replayed_until": None},
        "started_at": now_iso(),
        "finished_at": None,
        "error": None,
        "report": None,
    })
    run_id = run["id"]
    print(f"Created run {run_id} for experiment {args.experiment_id}")

    try:
        replayer = Replayer(session, run_id, args.symbol, events, args.speed)
        reader = Reader(session, run_id, args.symbol, specs, args.consistency, truth, lambda: replayer.watermark_us)
        sink = ReadingsFile(run_id)
        stop = threading.Event()
        replay_thread = threading.Thread(target=replayer.run, daemon=True)
        read_thread = threading.Thread(target=reader.run, args=(stop, sink.append), daemon=True)
        replay_thread.start()
        read_thread.start()

        while replay_thread.is_alive():
            replay_thread.join(timeout=2)
            print(f"    replayed to {iso(replayer.watermark_us)}   readings {sink.count}   failed reads {reader.failed_reads}")

        stop.set()
        read_thread.join()

        points = sink.points()
        sink.close()

        failed_rows = load_to_cassandra(session, run_id, points)
        report = build_report(points, [spec.id for spec in specs])
        records.update("run", run_id, {
            "status": "done",
            "finished_at": now_iso(),
            "progress": {"pct": 100, "replayed_until": iso(replayer.watermark_us)},
            "report": report,
            "error": f"{reader.failed_reads} reads failed" if reader.failed_reads else None,
        })

    except Exception as e:
        records.update("run", run_id, {
            "status": "failed",
            "finished_at": now_iso(),
            "error": str(e),
        })
        raise

    finally:
        cluster.shutdown()

    print(f"\ndone: {len(points)} readings saved ({failed_rows} failed), {reader.failed_reads} failed reads, "
          f"{replayer.failed_writes} failed writes")
    for signal_id, r in report.items():
        print(f"{signal_id}: error {r['avg_error']:.5%}  wrong calls {r['wrong_call_rate']:.1%}  "
              f"staleness p50/p99 {r['staleness_p50_ms']:.0f}/{r['staleness_p99_ms']:.0f} ms  "
              f"latency p50/p99 {r['latency_p50_ms']:.0f}/{r['latency_p99_ms']:.0f} ms  ({r['readings_count']} readings)")
    for store in records.stores:
        getattr(store, "close", lambda: None)()


if __name__ == "__main__":
    main()
