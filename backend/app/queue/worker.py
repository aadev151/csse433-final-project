import asyncio
import logging
import time
import random

from app.records.replicated import RecordNotFound
from app.replay_engine import merge_events_in_time_order, replay_events, run_replay_events
from app.runs.models import to_run
from app.experiments.models import to_experiment
from datetime import datetime, timezone, date
from dateutil.rrule import rrule, DAILY

log = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
CASSANDRA_RETRY_INTERVAL = 5.0
PROGRESS_STEPS = 10
PROGRESS_STEP_DELAY = 2.0


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

class RunWorker:

    def __init__(self, records, queue, cassandra_store, faults, broadcast):
        self._records = records
        self._queue = queue
        self._cassandra = cassandra_store
        self._faults = faults
        self._broadcast = broadcast

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

    def _execute_run(self, run_id):
        run_record, _ = self._records.get("run", run_id)
        if run_record is None: return

        experiment_id = run_record.get("experiment_id", "")

        experiment, _ = self._records.get("experiment", experiment_id)
        signal_ids = []
        symbols = []
        if experiment is not None:
            signal_ids = experiment.get("signal_ids", [])
            symbols = experiment.get("symbols", ["BTCUSDT"])

        now = _now_iso()
        started_fields = {
            "status": "running",
            "started_at": now
        }
        record = self._update_run(run_id, started_fields)
        if record is None: return
        
        # -------------------------------------------Work done for replay engine ------------------------------------------------------------------------------
        # Replaying events via replay engine:
        # Parameters to find/get/compute: symbol, hours, speed, trades_zip, quotes_zip, window_start, window_start_us, window_end_us
        run = to_run(record)
        symbols = run["symbols"]
        speed = run["replay_speed"]
        dates = run["dates"]
        start_date = date.fromisoformat(dates.start)
        end_date = date.fromisoformat(dates.end)
        hours = 24
        # https://www.geeksforgeeks.org/python/python-iterating-through-a-range-of-dates/
        for d in rrule(DAILY, dtstart=start_date, until=end_date):
            formatted_date = d.strftime("%Y-%m-%d")
            date_items = formatted_date.split("-")
            window_start = datetime(int(date_items[0]), int(date_items[1]), int(date_items[2]), 0, 0, tzinfo=timezone.utc)
            for symbol in symbols:
                # Strategically naming file names
                # for example, on my systems absolute address of these raw files downloaded looked like this
                # trades_zip = "C:/CSSE433/csse433-final-project/backend/raw-data/ETHUSDT-trades-2023-10-10.zip"
                # quotes_zip = "C:/CSSE433/csse433-final-project/backend/raw-data/ETHUSDT-bookTicker-2023-10-10.zip"
                trades_zip = f"{symbol}-trades-{formatted_date}.zip"
                quotes_zip = f"{symbol}-bookTicker-{formatted_date}.zip"
                

                # Replaying events for all the days in the date range
                run_replay_events(run_id, symbol, hours, speed, trades_zip, quotes_zip, window_start)
        
        # -----------------------------------------------End of Work done for replay engine----------------------------------------
        
        self._broadcast.send_status(run_id, "running")
        self._broadcast.send_faults(run_id, [])
        log.info("run %s started", run_id)


        # Temporary: simulated price until Features 8 & 9 provide real Cassandra reads
        base_price = 42000.0
        for step in range(1, PROGRESS_STEPS + 1):
            time.sleep(PROGRESS_STEP_DELAY)

            pct = round((step / PROGRESS_STEPS) * 100, 1)
            step_time = _now_iso()

            progress_fields = {
                "progress": {
                    "pct": pct,
                    "replayed_until": step_time
                }
            }
            record = self._update_run(run_id, progress_fields)
            if record is None: return

            self._broadcast.send_progress(run_id, pct, step_time)

            for signal_id in signal_ids:
                for symbol in symbols:
                    noise = random.uniform(-50, 50)
                    value = base_price + noise
                    truth = base_price + random.uniform(-10, 10)
                    staleness = random.uniform(0, 20)
                    latency = random.uniform(1, 15)

                    self._broadcast.send_reading(
                        run_id,
                        signal_id,
                        symbol,
                        step_time,
                        round(value, 2),
                        round(truth, 2),
                        round(staleness, 2),
                        round(latency, 2),
                    )

            base_price = base_price + random.uniform(-100, 100)

        finished_time = _now_iso()
        done_fields = {
            "status": "done",
            "finished_at": finished_time,
            "progress": {
                "pct": 100,
                "replayed_until": finished_time
            },
            "report": {},
        }
        self._update_run(run_id, done_fields)
        self._broadcast.send_progress(run_id, 100, finished_time)
        self._broadcast.send_status(run_id, "done")
        log.info("run %s finished", run_id)

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
            self._execute_run(run_id)

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