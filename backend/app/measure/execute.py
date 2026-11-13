import logging
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile
from cassandra.policies import RoundRobinPolicy

from app.measure.raw import read_quotes, read_trades
from app.measure.reader import Reader
from app.measure.replay import Replayer, merge_events
from app.measure.store import ReadingsFile, load_to_cassandra
from app.measure.truth import TruthBook


log = logging.getLogger(__name__)

PROGRESS_INTERVAL_S = 1.0


def iso(us):
    return datetime.fromtimestamp(us / 1_000_000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def day_start_us(day):
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1_000_000)


def find_market_file(raw_data_dirs, symbol, kind, day):
    name = f"{symbol}-{kind}-{day}.zip"
    for folder in raw_data_dirs:
        path = Path(folder) / name
        if path.is_file():
            return path

    raise FileNotFoundError(f"could not find {kind} file for {symbol} on {day} in {raw_data_dirs}")


def open_market_session(hosts, port):
    profile = ExecutionProfile(load_balancing_policy=RoundRobinPolicy(), request_timeout=5)
    cluster = Cluster(list(hosts), execution_profiles={EXEC_PROFILE_DEFAULT: profile}, port=port, protocol_version=5, connect_timeout=10)
    try:
        session = cluster.connect()
        return cluster, session
    except Exception:
        cluster.shutdown()
        raise


def measure_symbol(session, run_id, symbol, day, window_s, speed, consistency, specs, raw_data_dirs, on_point, on_progress, should_stop):
    start_us = day_start_us(day)
    end_us = start_us + int(window_s * 1_000_000)
    trades = read_trades(find_market_file(raw_data_dirs, symbol, "trades", day), start_us, end_us)
    quotes = read_quotes(find_market_file(raw_data_dirs, symbol, "bookTicker", day), start_us, end_us)
    log.info("run %s: %s has %d trades and %d quotes in the window", run_id, symbol, len(trades), len(quotes))

    stop = threading.Event()
    truth = TruthBook(trades, quotes)
    replayer = Replayer(session, run_id, symbol, merge_events(trades, quotes), speed, stop)
    reader = Reader(session, run_id, symbol, specs, consistency, truth, lambda: replayer.watermark_us)
    sink = ReadingsFile(run_id)

    def keep(point):
        sink.append(point)
        on_point(point)

    replay_thread = threading.Thread(target=replayer.run, daemon=True)
    read_thread = threading.Thread(target=reader.run, args=(stop, keep), daemon=True)
    replay_thread.start()
    read_thread.start()

    try:
        while replay_thread.is_alive():
            replay_thread.join(timeout=PROGRESS_INTERVAL_S)
            on_progress(replayer.progress(), iso(replayer.watermark_us))
            if should_stop():
                stop.set()
    finally:
        stop.set()
        replay_thread.join()
        read_thread.join()

    points = sink.points()
    sink.close()

    failed_rows = load_to_cassandra(session, run_id, points)
    stats = {
        "failed_reads": reader.failed_reads,
        "failed_writes": replayer.failed_writes,
        "failed_rows": failed_rows,
        "replayed_until": iso(replayer.watermark_us),
    }

    return points, stats
