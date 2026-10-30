import asyncio
import logging
import time

from app.records.replicated import RecordNotFound

log = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
CASSANDRA_RETRY_INTERVAL = 5.0
PROGRESS_STEPS = 10
PROGRESS_STEP_DELAY = 2.0


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

class RunWorker:

    def __init__(self, records, queue, cassandra_store, faults):
        self._records = records
        self._queue = queue
        self._cassandra = cassandra_store
        self._faults = faults

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
        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        started_fields = {"status": "running", "started_at": now}
        record = self._update_run(run_id, started_fields)
        if record is None:
            return

        log.info("run %s started", run_id)
        for step in range(1, PROGRESS_STEPS + 1):
            time.sleep(PROGRESS_STEP_DELAY)
            pct = round((step / PROGRESS_STEPS) * 100, 1)
            progress_fields = {"progress": {
                "pct": pct,
                "replayed_until": None,
                }
            }
            record = self._update_run(run_id, progress_fields)
            if record is None:
                return
        finished_time = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        done_fields = {
            "status": "done",
            "finished_at": finished_time,
            "progress": {
                "pct": 100,
                "replayed_until": None
            },
            "report": {},
        }
        self._update_run(run_id, done_fields)
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
            self._queue.push([run_id])
            return False

        if status == "waiting_for_cassandra":
            queued_fields = {"status": "queued"}
            self._update_run(run_id, queued_fields)

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
