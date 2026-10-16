import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.datasets.binance import (
    DataInvalid,
    DownloadFailed,
    DownloadNotFound,
    HttpFetcher,
    checksum_url,
    file_name,
    file_url,
    inspect_trades_zip,
    parse_checksum,
    sha256_file,
)
from app.records.replicated import RecordNotFound

log = logging.getLogger(__name__)

RECORD_TYPE = "dataset"
IN_PROGRESS = ("downloading", "verifying")


class ImportRequestInvalid(Exception):
    pass


def utc_today():
    return datetime.now(timezone.utc).date()


def dataset_id(symbol, kind, day):
    return f"{symbol}-{kind}-{day.isoformat()}"


class DatasetImporter:
    """Downloads and verifies Binance daily files, one day at a time, in the background."""

    def __init__(self, records, data_dir, fetcher=None, today=utc_today, run_inline=False):
        self.records = records
        self.root = Path(data_dir) / "binance"
        self.fetcher = fetcher or HttpFetcher()
        self.today = today
        self._executor = None if run_inline else ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="dataset-import"
        )

    # Requests

    def start_import(self, symbol, kind, days):
        """Create or reuse one record per day and queue the days that need work.

        Returns (records, writes). Days already ready or in progress are returned as-is.
        """
        latest = self.today() - timedelta(days=1)
        if max(days) > latest:
            raise ImportRequestInvalid(
                f"Binance publishes each day's file the next day; the latest day available is {latest.isoformat()}"
            )
        results = []
        writes = []
        to_run = []
        for day in days:
            record_id = dataset_id(symbol, kind, day)
            existing, _ = self.records.get(RECORD_TYPE, record_id)
            if existing is not None and existing["status"] != "failed":
                results.append(existing)
                continue
            fields = self._fresh_fields(symbol, kind, day)
            if existing is None:
                record, write = self.records.create(RECORD_TYPE, fields, record_id=record_id)
            else:
                record, write = self.records.update(RECORD_TYPE, record_id, fields)
            results.append(record)
            writes.append(write)
            to_run.append(record_id)
        for record_id in to_run:
            self._submit(record_id)
        return results, writes

    def delete(self, record_id):
        record, _ = self.records.get(RECORD_TYPE, record_id)
        if record is None:
            raise RecordNotFound(RECORD_TYPE, record_id)
        write = self.records.delete(RECORD_TYPE, record_id)
        self._remove_files(record)
        return write

    def recover_interrupted(self):
        """Mark imports left unfinished by a restart as failed so they can be retried."""
        records, _ = self.records.list(RECORD_TYPE)
        for record in records:
            if record["status"] in IN_PROGRESS:
                self._remove_files(record, keep_complete=False)
                try:
                    self._fail(record["id"], "Import was interrupted by a backend restart; import this day again to retry")
                except RecordNotFound:
                    pass

    def shutdown(self):
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    # Background work

    def _submit(self, record_id):
        if self._executor is None:
            self._run(record_id)
        else:
            self._executor.submit(self._run, record_id)

    def _run(self, record_id):
        record, _ = self.records.get(RECORD_TYPE, record_id)
        if record is None:
            return
        try:
            self._import_one(record)
        except RecordNotFound:
            log.info("dataset %s was deleted during import", record_id)
            self._remove_files(record, keep_complete=False)
        except Exception as error:
            log.exception("dataset import failed for %s", record_id)
            try:
                self._fail(record_id, f"Unexpected error: {error}")
            except RecordNotFound:
                pass

    def _import_one(self, record):
        record_id = record["id"]
        symbol = record["symbol"]
        kind = record["kind"]
        day = date.fromisoformat(record["day"])
        dest = self._file_path(symbol, kind, day)
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.fetcher.download(file_url(symbol, kind, day), dest)
        except DownloadNotFound:
            self._fail(record_id, f"Binance has no {kind} file for {symbol} on {day.isoformat()}")
            return
        except DownloadFailed as error:
            self._fail(record_id, f"Download failed: {error}")
            return

        self.records.update(
            RECORD_TYPE,
            record_id,
            {"status": "verifying", "size_bytes": dest.stat().st_size, "path": str(dest)},
        )

        try:
            expected = parse_checksum(self.fetcher.read_text(checksum_url(symbol, kind, day)), dest.name)
        except DownloadNotFound:
            self._fail(record_id, "Binance has no checksum file for this day")
            return
        except (DownloadFailed, DataInvalid) as error:
            self._fail(record_id, f"Could not read the checksum: {error}")
            return

        if sha256_file(dest) != expected:
            dest.unlink(missing_ok=True)
            self._fail(
                record_id,
                "Checksum mismatch: the download was corrupted; import this day again to retry",
                checksum_ok=False,
                path=None,
            )
            return

        try:
            stats = inspect_trades_zip(dest, day)
        except DataInvalid as error:
            self._fail(record_id, f"File failed validation: {error}", checksum_ok=True)
            return

        self.records.update(
            RECORD_TYPE,
            record_id,
            {
                "status": "ready",
                "checksum_ok": True,
                "row_count": stats.row_count,
                "first_ts_us": stats.first_ts_us,
                "last_ts_us": stats.last_ts_us,
                "timestamp_unit": stats.timestamp_unit,
                "id_gaps": stats.id_gaps,
                "error": None,
            },
        )

    # Helpers

    def _fail(self, record_id, message, **extra):
        self.records.update(RECORD_TYPE, record_id, {"status": "failed", "error": message, **extra})

    def _file_path(self, symbol, kind, day):
        return self.root / symbol / kind / file_name(symbol, kind, day)

    def _remove_files(self, record, keep_complete=False):
        try:
            path = self._file_path(record["symbol"], record["kind"], date.fromisoformat(record["day"]))
        except (KeyError, ValueError, TypeError):
            return
        path.with_name(path.name + ".part").unlink(missing_ok=True)
        if not keep_complete:
            path.unlink(missing_ok=True)

    def _fresh_fields(self, symbol, kind, day):
        return {
            "symbol": symbol,
            "kind": kind,
            "day": day.isoformat(),
            "status": "downloading",
            "row_count": None,
            "size_bytes": None,
            "checksum_ok": None,
            "error": None,
            "path": None,
            "first_ts_us": None,
            "last_ts_us": None,
            "timestamp_unit": None,
            "id_gaps": None,
        }