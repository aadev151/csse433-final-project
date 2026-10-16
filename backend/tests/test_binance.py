import hashlib
from datetime import date

import pytest

from app.datasets.binance import (
    DataInvalid,
    HttpFetcher,
    checksum_url,
    file_url,
    inspect_trades_zip,
    parse_checksum,
    sha256_file,
)
from tests.dataset_helpers import day_start_ms, trade_rows, zip_bytes

DAY = date(2024, 1, 1)
DAY_2025 = date(2025, 1, 1)


def write_zip(tmp_path, data):
    path = tmp_path / "file.zip"
    path.write_bytes(data)
    return path


# URLs

def test_file_url_format():
    assert file_url("BTCUSDT", "trades", DAY) == (
        "https://data.binance.vision/data/spot/daily/trades/BTCUSDT/BTCUSDT-trades-2024-01-01.zip"
    )
    assert checksum_url("BTCUSDT", "trades", DAY).endswith("BTCUSDT-trades-2024-01-01.zip.CHECKSUM")


def test_url_rejects_unknown_symbol_kind_or_day_type():
    with pytest.raises(ValueError):
        file_url("DOGEUSDT", "trades", DAY)
    with pytest.raises(ValueError):
        file_url("BTCUSDT", "quotes", DAY)
    with pytest.raises(TypeError):
        file_url("BTCUSDT", "trades", "2024-01-01")


def test_fetcher_refuses_other_hosts(tmp_path):
    fetcher = HttpFetcher()
    with pytest.raises(ValueError):
        fetcher.download("https://example.com/file.zip", tmp_path / "x.zip")
    with pytest.raises(ValueError):
        fetcher.read_text("http://data.binance.vision/insecure")


# Checksums

def test_parse_checksum():
    digest = "a" * 64
    assert parse_checksum(f"{digest}  BTCUSDT-trades-2024-01-01.zip\n", "BTCUSDT-trades-2024-01-01.zip") == digest


def test_parse_checksum_rejects_wrong_file_name():
    with pytest.raises(DataInvalid):
        parse_checksum(f"{'a' * 64}  OTHER.zip", "BTCUSDT-trades-2024-01-01.zip")


@pytest.mark.parametrize("text", ["", "not-a-hash file.zip", "abc123 file.zip"])
def test_parse_checksum_rejects_malformed(text):
    with pytest.raises(DataInvalid):
        parse_checksum(text, "file.zip")


def test_sha256_file(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"hello")
    assert sha256_file(path) == hashlib.sha256(b"hello").hexdigest()


# File inspection

def test_inspect_counts_rows_and_normalizes_ms_to_us(tmp_path):
    stats = inspect_trades_zip(write_zip(tmp_path, zip_bytes(trade_rows(DAY, count=3))), DAY)
    assert stats.row_count == 3
    assert stats.timestamp_unit == "ms"
    assert stats.first_ts_us == day_start_ms(DAY) * 1000
    assert stats.last_ts_us == (day_start_ms(DAY) + 2000) * 1000
    assert stats.id_gaps == 0


def test_inspect_detects_microseconds(tmp_path):
    stats = inspect_trades_zip(write_zip(tmp_path, zip_bytes(trade_rows(DAY_2025, unit="us"))), DAY_2025)
    assert stats.timestamp_unit == "us"
    assert stats.first_ts_us == day_start_ms(DAY_2025) * 1000


def test_inspect_skips_header_row(tmp_path):
    header = ["id", "price", "qty", "quote_qty", "time", "is_buyer_maker", "is_best_match"]
    stats = inspect_trades_zip(write_zip(tmp_path, zip_bytes(trade_rows(DAY), header=header)), DAY)
    assert stats.row_count == 3


def test_inspect_counts_id_gaps(tmp_path):
    rows = trade_rows(DAY, count=3)
    rows[2][0] = "10"
    assert inspect_trades_zip(write_zip(tmp_path, zip_bytes(rows)), DAY).id_gaps == 7


def mutate(rows, index, column, value):
    rows[index][column] = value
    return rows


@pytest.mark.parametrize(
    "rows",
    [
        mutate(trade_rows(DAY), 1, 4, str(day_start_ms(DAY) - 1)),           # before the day
        mutate(trade_rows(DAY), 2, 4, str(day_start_ms(DAY) + 86_400_000)),  # after the day
        mutate(trade_rows(DAY), 2, 4, str(day_start_ms(DAY))),               # out of order
        mutate(trade_rows(DAY), 2, 0, "1"),                                  # id not increasing
        mutate(trade_rows(DAY), 1, 1, "abc"),                                # non-numeric price
        mutate(trade_rows(DAY), 1, 2, "0"),                                  # zero quantity
        mutate(trade_rows(DAY), 1, 1, "-5"),                                 # negative price
        mutate(trade_rows(DAY), 1, 4, str((day_start_ms(DAY) + 1000) * 1000)),  # mixed units
        [row[:6] for row in trade_rows(DAY)],                                # wrong column count
        [],                                                                  # empty file
    ],
)
def test_inspect_rejects_bad_files(tmp_path, rows):
    with pytest.raises(DataInvalid):
        inspect_trades_zip(write_zip(tmp_path, zip_bytes(rows)), DAY)


def test_inspect_rejects_archive_with_two_files(tmp_path):
    data = zip_bytes(trade_rows(DAY), extra_members=[("other.csv", "x")])
    with pytest.raises(DataInvalid):
        inspect_trades_zip(write_zip(tmp_path, data), DAY)


def test_inspect_rejects_non_zip(tmp_path):
    with pytest.raises(DataInvalid):
        inspect_trades_zip(write_zip(tmp_path, b"not a zip"), DAY)