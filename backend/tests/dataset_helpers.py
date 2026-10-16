import hashlib
import io
import zipfile
from datetime import datetime, timezone

from app.datasets.binance import DownloadNotFound, checksum_url, file_name, file_url


def day_start_ms(day):
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return int(start.timestamp()) * 1000


def trade_rows(day, count=3, unit="ms", first_id=1):
    base = day_start_ms(day)
    rows = []
    for n in range(count):
        ts = base + n * 1000
        if unit == "us":
            ts *= 1000
        rows.append([str(first_id + n), "42000.5", "0.01", "420.005", str(ts), "True", "True"])
    return rows


def zip_bytes(rows, member_name="data.csv", header=None, extra_members=()):
    lines = []
    if header is not None:
        lines.append(",".join(header))
    lines.extend(",".join(row) for row in rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member_name, "\n".join(lines) + "\n")
        for name, content in extra_members:
            archive.writestr(name, content)
    return buffer.getvalue()


class FakeFetcher:
    """Serves prepared files by URL; anything else is a 404."""

    def __init__(self):
        self.files = {}
        self.downloads = []
        self.on_download = None

    def publish(self, symbol, day, rows=None, data=None, checksum=None, kind="trades"):
        if data is None:
            data = zip_bytes(rows if rows is not None else trade_rows(day))
        name = file_name(symbol, kind, day)
        digest = checksum if checksum is not None else hashlib.sha256(data).hexdigest()
        self.files[file_url(symbol, kind, day)] = data
        self.files[checksum_url(symbol, kind, day)] = f"{digest}  {name}\n".encode()

    def download(self, url, dest):
        self.downloads.append(url)
        if self.on_download is not None:
            self.on_download(url)
        if url not in self.files:
            raise DownloadNotFound(url)
        dest.write_bytes(self.files[url])

    def read_text(self, url):
        if url not in self.files:
            raise DownloadNotFound(url)
        return self.files[url].decode()