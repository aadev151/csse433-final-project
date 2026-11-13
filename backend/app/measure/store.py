import json
import tempfile

from cassandra.concurrent import execute_concurrent_with_args


INSERT = (
    "INSERT INTO market.readings (run_id, signal_id, symbol, t_us, market_us, value, truth, staleness_ms, latency_ms) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
SELECT = (
    "SELECT t_us, market_us, value, truth, staleness_ms, latency_ms FROM market.readings "
    "WHERE run_id = ? AND signal_id = ? AND symbol = ? AND t_us >= ? AND t_us <= ?"
)

_prepared ={}


def _prepare(session, query):
    key = (id(session), query)
    if key not in _prepared:
        _prepared[key] = session.prepare(query)
    return _prepared[key]


class ReadingsFile:
    def __init__(self, run_id):
        self._file = tempfile.NamedTemporaryFile("w", prefix=f"readings-{run_id}-", suffix=".jsonl", delete=False)
        self.path = self._file.name
        self.count = 0

    def append(self, point):
        self._file.write(json.dumps(point) + "\n")
        self.count += 1

    def points(self):
        self._file.flush()
        with open(self.path) as f:
            return [json.loads(line) for line in f]

    def close(self):
        self._file.close()



def load_to_cassandra(session, run_id, points, concurrency=64):
    statement = _prepare(session, INSERT)
    args = [
        (run_id, point["signal_id"], point["symbol"], point["t_us"], point["market_us"],
         point["value"], point["truth"], point["staleness_ms"], point["latency_ms"])
        for point in points
    ]
    results = execute_concurrent_with_args(session, statement, args, concurrency=concurrency, raise_on_first_error=False)

    return sum(1 for ok, _ in results if not ok)


def fetch_readings(session, run_id, signal_id, symbol, from_us, to_us):
    statement = _prepare(session, SELECT)
    return list(session.execute(statement, (run_id, signal_id, symbol, from_us, to_us)))
