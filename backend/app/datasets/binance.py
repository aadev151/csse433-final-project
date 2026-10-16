import csv
import hashlib
import io
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.records.checks import require_choice

ALLOWED_URL_PREFIX = "https://data.binance.vision/"
BASE_URL = "https://data.binance.vision/data/spot/daily"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
ARCHIVE_NAMES = {"trades": "trades"}  # kind -> Binance folder name; quotes not available yet

TRADE_COLUMNS = 7
MICROSECOND_THRESHOLD = 10**15  # ms timestamps are ~13 digits, us timestamps ~16
MICROSECONDS_PER_DAY = 86_400 * 1_000_000
CHUNK_SIZE = 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class DownloadNotFound(Exception):
    pass


class DownloadFailed(Exception):
    pass


class DataInvalid(Exception):
    pass


@dataclass
class TradeFileStats:
    row_count: int
    first_ts_us: int
    last_ts_us: int
    timestamp_unit: str
    id_gaps: int


def _check_target(symbol, kind, day):
    require_choice("symbol", symbol, SYMBOLS)
    require_choice("kind", kind, tuple(ARCHIVE_NAMES))
    if not isinstance(day, date) or isinstance(day, datetime):
        raise TypeError(f"day must be a date, got {type(day).__name__}")


def file_name(symbol, kind, day):
    _check_target(symbol, kind, day)
    return f"{symbol}-{ARCHIVE_NAMES[kind]}-{day.isoformat()}.zip"


def file_url(symbol, kind, day):
    name = file_name(symbol, kind, day)  # runs the checks before ARCHIVE_NAMES is used
    return f"{BASE_URL}/{ARCHIVE_NAMES[kind]}/{symbol}/{name}"


def checksum_url(symbol, kind, day):
    return file_url(symbol, kind, day) + ".CHECKSUM"


class HttpFetcher:
    """Downloads from data.binance.vision only."""

    def __init__(self, timeout_seconds=30):
        self.timeout = timeout_seconds

    def download(self, url, dest):
        self._check_url(url)
        part = dest.with_name(dest.name + ".part")
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response, open(part, "wb") as file:
                while chunk := response.read(CHUNK_SIZE):
                    file.write(chunk)
        except urllib.error.HTTPError as error:
            part.unlink(missing_ok=True)
            if error.code == 404:
                raise DownloadNotFound(url) from error
            raise DownloadFailed(f"HTTP {error.code} for {url}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            part.unlink(missing_ok=True)
            raise DownloadFailed(str(error)) from error
        part.replace(dest)

    def read_text(self, url):
        self._check_url(url)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                return response.read(4096).decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise DownloadNotFound(url) from error
            raise DownloadFailed(f"HTTP {error.code} for {url}") from error
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError) as error:
            raise DownloadFailed(str(error)) from error

    def _check_url(self, url):
        if not isinstance(url, str) or not url.startswith(ALLOWED_URL_PREFIX):
            raise ValueError(f"refusing to download from outside {ALLOWED_URL_PREFIX}: {url!r}")


def parse_checksum(text, expected_file_name):
    parts = text.strip().split()
    if not parts or not SHA256_PATTERN.match(parts[0]):
        raise DataInvalid("checksum file does not start with a SHA-256 hash")
    if len(parts) >= 2 and parts[-1].lstrip("*") != expected_file_name:
        raise DataInvalid(f"checksum file is for {parts[-1]!r}, not {expected_file_name!r}")
    return parts[0].lower()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _day_bounds_us(day):
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    start_us = int(start.timestamp()) * 1_000_000
    return start_us, start_us + MICROSECONDS_PER_DAY


def inspect_trades_zip(path, day):
    """Check every row of a Binance spot trades file and summarize it.

    Columns: trade id, price, qty, quote qty, time, buyer is maker, best match.
    """
    start_us, end_us = _day_bounds_us(day)
    row_count = 0
    first_ts = None
    last_ts = None
    last_id = None
    unit = None
    id_gaps = 0
    try:
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            if len(members) != 1 or not members[0].endswith(".csv"):
                raise DataInvalid(f"expected exactly one CSV file in the archive, found {members}")
            with archive.open(members[0]) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
                for line_number, row in enumerate(reader, start=1):
                    if not row:
                        continue
                    if line_number == 1 and not row[0].strip().isdigit():
                        continue  # header row
                    if len(row) != TRADE_COLUMNS:
                        raise DataInvalid(f"line {line_number}: expected {TRADE_COLUMNS} columns, got {len(row)}")
                    try:
                        trade_id = int(row[0])
                        price = float(row[1])
                        qty = float(row[2])
                        raw_ts = int(row[4])
                    except ValueError as error:
                        raise DataInvalid(f"line {line_number}: {error}") from error
                    if price <= 0 or qty <= 0:
                        raise DataInvalid(f"line {line_number}: price and quantity must be positive")

                    row_unit = "us" if raw_ts >= MICROSECOND_THRESHOLD else "ms"
                    if unit is None:
                        unit = row_unit
                    elif row_unit != unit:
                        raise DataInvalid(f"line {line_number}: file mixes millisecond and microsecond timestamps")
                    ts_us = raw_ts if unit == "us" else raw_ts * 1000

                    if not start_us <= ts_us < end_us:
                        raise DataInvalid(f"line {line_number}: timestamp is outside {day.isoformat()}")
                    if last_id is not None:
                        if trade_id <= last_id:
                            raise DataInvalid(f"line {line_number}: trade ids are not increasing")
                        id_gaps += trade_id - last_id - 1
                    if last_ts is not None and ts_us < last_ts:
                        raise DataInvalid(f"line {line_number}: timestamps are out of order")

                    if first_ts is None:
                        first_ts = ts_us
                    last_ts = ts_us
                    last_id = trade_id
                    row_count += 1
    except zipfile.BadZipFile as error:
        raise DataInvalid(f"not a valid ZIP file: {error}") from error
    except UnicodeDecodeError as error:
        raise DataInvalid(f"file is not valid UTF-8 text: {error}") from error

    if row_count == 0:
        raise DataInvalid("file contains no trades")
    return TradeFileStats(
        row_count=row_count,
        first_ts_us=first_ts,
        last_ts_us=last_ts,
        timestamp_unit=unit,
        id_gaps=id_gaps,
    )