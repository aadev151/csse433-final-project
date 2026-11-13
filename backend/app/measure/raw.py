import csv
import io
import zipfile


def to_us(raw):
    value = int(raw)
    return value * 1000 if value < 10 ** 15 else value


def _rows(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(archive.namelist()[0]) as handle:
            for row in csv.reader(io.TextIOWrapper(handle, encoding='utf-8')):
                if row and row[0].isdigit():
                    yield row


def read_trades(zip_path, start_us, end_us):
    # Cols: 0 id, 1 price, 2 qty, 3 quote_qty, 4 time, 5 is_buyer_maker
    trades = []
    for row in _rows(zip_path):
        event_us = to_us(row[4])
        if event_us < start_us:
            continue
        if event_us >= end_us:
            break

        trades.append((event_us, int(row[0]), float(row[1]), float(row[2]), row[5].lower() == "true"))
    
    trades.sort()
    return trades


def read_quotes(zip_path, start_us, end_us):
    # Cols: 0 update_id, 1 bid_px, 2 bid_qty, 3 ask_px, 4 ask_qty, 5 transaction_time, 6 event_time
    quotes = []
    for row in _rows(zip_path):
        event_us = to_us(row[5])
        if event_us < start_us:
            continue
        if event_us >= end_us:
            break

        quotes.append((event_us, int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4])))

    quotes.sort()
    return quotes
