import asyncio
import logging
import time

from app.measure.execute import iso, measure_symbol, open_market_session
from app.measure.report import build_report
from app.measure.signals import spec_from_signal
from app.records.replicated import RecordNotFound


log = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
CASSANDRA_RETRY_INTERVAL = 5.0


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

class RunWorker:

    def __init__(self, records, queue, cassandra_store, faults, broadcast, settings):
        self._records = records
        self._queue = queue
        self._cassandra = cassandra_store
        self._faults = faults
        self._broadcast = broadcast
        self._settings = settings

    def _is_cassandra_up(self):
        try:
            self._cassandra.ping()
            return True
        except Exception:
            return False

    def _update_run(self, run_id, fields):
        try:
            record, _ = self._records.update("run", run_id, fields)
            return record
        except RecordNotFound:
            log.warning("run %s was deleted while being processed", run_id)
            return None

    def _is_cancelled(self, run_id):
        record, _ = self._records.get("run", run_id)
        if record is None:
            return True
        return record.get("status") == "cancelled"

    def _run_inputs(self, run):
        experiment, _ = self._records.get("experiment", run.get("experiment_id", ""))
        if experiment is None:
            raise ValueError("this run's experiment no longer exists")

        symbols = run.get("symbols") or experiment["symbols"]
        speed = run.get("replay_speed") or experiment["replay_speed"]
        dates = run.get("dates") or experiment["dates"]

        specs = []
        for signal_id in experiment["signal_ids"]:
            signal, _ = self._records.get("signal", signal_id)
            if signal is None:
                log.warning("run %s: signal %s no longer exists, skipping it", run["id"], signal_id)
                continue
            specs.append(spec_from_signal(signal))
        if not specs:
            raise ValueError("this experiment has no signals that still exist")

        return symbols, speed, dates["start"], specs

    def _send_point(self, run_id):
        def send(point):
            self._broadcast.send_reading(
                run_id, point["signal_id"], point["symbol"], iso(point["t_us"]),
                point["value"], point["truth"], point["staleness_ms"], point["latency_ms"],
            )
        return send
    
    def _report_progress(self, run_id, symbol_number, symbol_count, fraction, replayed_until):
        pct = round((symbol_number + fraction) / symbol_count * 100, 1)
        self._last_replayed_until = replayed_until
        self._update_run(run_id, {"progress": {"pct": pct, "replayed_until": replayed_until}})
        self._broadcast.send_progress(run_id, pct, replayed_until)

    def _execute_run(self, run_id, active_faults):
        run, _ = self._records.get("run", run_id)
        if run is None:
            return
        symbols, speed, day, specs = self._run_inputs(run)
        consistency = run["config"]["consistency"]

        if self._update_run(run_id, {"status": "running", "started_at": _now_iso()}) is None:
            return
        self._broadcast.send_status(run_id, "running")
        self._broadcast.send_faults(run_id, active_faults)
        log.info("run %s started: %s at %s, speed %sx, day %s", run_id, symbols, consistency, speed, day)

        points = []
        failed = {"failed_reads": 0, "failed_writes": 0, "failed_rows": 0}
        self._last_replayed_until = None
        cluster, session = open_market_session(self._settings.cassandra_hosts, self._settings.cassandra_port)
        try:
            for index, symbol in enumerate(symbols):

                def on_progress(fraction, until):
                    self._report_progress(run_id, index, len(symbols), fraction, until)

                def should_stop():
                    return self._is_cancelled(run_id)

                symbol_points, stats = measure_symbol(
                    session, run_id, symbol, day,
                    self._settings.replay_window_seconds, speed, consistency, specs,
                    self._settings.raw_data_dirs,
                    on_point=self._send_point(run_id),
                    on_progress=on_progress,
                    should_stop=should_stop,
                )
                points.extend(symbol_points)
                for key in failed:
                    failed[key] += stats[key]
                if self._is_cancelled(run_id):
                    break
        finally:
            cluster.shutdown()

        if self._is_cancelled(run_id):
            log.info("run %s was cancelled", run_id)
            self._broadcast.send_status(run_id, "cancelled")
            return

        report = build_report(points, [spec.id for spec in specs])
        notes = [f"{count} {key.replace('_', ' ')}" for key, count in failed.items() if count]

        self._update_run(run_id, {
            "status": "done",
            "finished_at": _now_iso(),
            "progress": {"pct": 100, "replayed_until": self._last_replayed_until},
            "report": report,
            "error": "; ".join(notes) or None,
        })
        self._broadcast.send_progress(run_id, 100, self._last_replayed_until)
        self._broadcast.send_status(run_id, "done")
        log.info("run %s finished with %d readings (%s)", run_id, len(points), notes or "no failures")
    
    def _clear_faults(self, run_id, active, started_at):
        try:
            self._faults.clear(active)
        except Exception:
            log.exception("failed to clear faults for run %s", run_id)

        if active:
            ended_at = _now_iso()
            faults = [{**fault, "start": started_at, "end": ended_at} for fault in active]
            self._update_run(run_id, {"faults": faults})

    def _process_one(self, run_id):
        record, _ = self._records.get("run", run_id)
        if record is None:
            log.warning("run %s not found, skipping", run_id)
            return True

        status = record.get("status")
        if status in ("done", "failed", "cancelled"):
            log.info("run %s already %s, skipping", run_id, status)
            return True

        if not self._is_cassandra_up():
            log.warning("cassandra is down, holding run %s", run_id)
            waiting_fields = {"status": "waiting_for_cassandra"}
            self._update_run(run_id, waiting_fields)
            self._broadcast.send_status(run_id, "waiting_for_cassandra")
            self._queue.push([run_id])
            return False

        if status == "waiting_for_cassandra":
            queued_fields = {"status": "queued"}
            self._update_run(run_id, queued_fields)
            self._broadcast.send_status(run_id, "queued")

        active = []
        started_at = _now_iso()
        try:
            active = self._faults.apply(record["config"])
            faults = [{**fault, "start": started_at, "end": None} for fault in active]
            self._update_run(run_id, {"faults": faults})
            self._execute_run(run_id, active)

        except Exception as error:
            log.exception("run %s failed", run_id)
            self._update_run(run_id, {"status": "failed", "finished_at": _now_iso(), "error": str(error)})
            self._broadcast.send_status(run_id, "failed")

        finally:
            self._clear_faults(run_id, active, started_at)

        return True

    async def run_forever(self):
        log.info("run worker started")
        while True:
            run_id = await asyncio.to_thread(self._queue.pop)
            if run_id is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            log.info("picked up run %s from queue", run_id)
            success = await asyncio.to_thread(self._process_one, run_id)
            if not success:
                await asyncio.sleep(CASSANDRA_RETRY_INTERVAL)
