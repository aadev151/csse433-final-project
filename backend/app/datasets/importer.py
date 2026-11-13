import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BINANCE_BASE_URL = "https://data.binance.vision"

# The API calls best bid/ask data "quotes", but Binance (and the rest of our code,
# see find_market_file) names those files "bookTicker".
FILE_KINDS = {"trades": "trades", "quotes": "bookTicker"}

# Trades come from the spot market. Binance does not publish bookTicker for spot at all,
# so quotes come from the USD-M futures folder (checked by hand against data.binance.vision:
# the spot bookTicker path returns 404). Our existing raw-data files match these checksums.
REMOTE_FOLDERS = {
    "trades": "data/spot/daily/trades",
    "bookTicker": "data/futures/um/daily/bookTicker",
}

# Seconds to wait on any single network read. urllib applies it per socket operation,
# so a slow but steady big download is fine, while a stalled one gives up.
DOWNLOAD_TIMEOUT_SECONDS = 30
CHUNK_SIZE = 1024 * 1024

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DownloadError(Exception):
    pass


def file_name(symbol, kind, day):
    return f"{symbol}-{FILE_KINDS[kind]}-{day}.zip"


def remote_url(symbol, kind, day):
    file_kind = FILE_KINDS[kind]
    return f"{BINANCE_BASE_URL}/{REMOTE_FOLDERS[file_kind]}/{symbol}/{file_name(symbol, kind, day)}"


def _open(url, symbol, kind, day):
    try:
        return urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    except HTTPError as error:
        if error.code == 404:
            raise DownloadError(f"Binance has no {kind} file for {symbol} on {day}") from error
        raise DownloadError(f"Binance returned HTTP {error.code} for {url}") from error
    except (URLError, OSError) as error:
        raise DownloadError(f"Could not reach Binance: {error}") from error


def fetch_expected_checksum(symbol, kind, day):
    # The .CHECKSUM file is one line: "<sha256 hex>  <file name>"
    url = remote_url(symbol, kind, day) + ".CHECKSUM"
    try:
        with _open(url, symbol, kind, day) as response:
            text = response.read(4096).decode("utf-8", errors="replace")
    except OSError as error:
        raise DownloadError(f"Could not read the checksum file: {error}") from error

    parts = text.split()
    if not parts or not SHA256_PATTERN.match(parts[0].lower()):
        raise DownloadError(f"Checksum file for {file_name(symbol, kind, day)} is not valid")
    return parts[0].lower()


def _download_to(url, handle, symbol, kind, day):
    # Hash while writing so we never have to read a 100MB+ file a second time.
    digest = hashlib.sha256()
    size = 0
    try:
        with _open(url, symbol, kind, day) as response:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except OSError as error:
        raise DownloadError(f"Download of {file_name(symbol, kind, day)} failed: {error}") from error
    return size, digest.hexdigest()


def _remove_quietly(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def download_and_verify(folder, symbol, kind, day):
    """Downloads one daily file into folder and checks its sha256.

    Returns the size in bytes. Raises DownloadError if anything goes wrong, and in that
    case nothing new is left in folder (no partial or unverified zip).
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = file_name(symbol, kind, day)
    expected = fetch_expected_checksum(symbol, kind, day)

    # Download into a temp file in the same folder, then rename it. The rename is atomic
    # (same disk), so other code never sees a half-written zip. The ".part" suffix also
    # keeps it out of the "*.zip" scan in GET /api/datasets.
    descriptor, temp_path = tempfile.mkstemp(dir=folder, prefix=name + ".", suffix=".part")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            size, actual = _download_to(remote_url(symbol, kind, day), handle, symbol, kind, day)
        if actual != expected:
            raise DownloadError(f"Checksum mismatch for {name}: expected {expected}, got {actual}")

        # Keep Binance's checksum next to the zip (same format as the files already in raw-data).
        (folder / (name + ".CHECKSUM")).write_text(f"{expected}  {name}\n")
        os.replace(temp_path, folder / name)
    except BaseException:
        # BaseException so even a cancelled request does not leave a .part file behind
        _remove_quietly(temp_path)
        raise
    return size
