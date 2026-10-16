import json
import re
import threading
import time

from cassandra import ConsistencyLevel, DriverException, RequestExecutionException
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile, NoHostAvailable
from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy

from app.records.checks import require_choice, require_record, require_record_type, require_str
from app.records.stores import RecordStore, StoreUnavailable

KEYSPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
CONSISTENCY_LEVELS = ("ONE", "TWO", "QUORUM", "LOCAL_QUORUM", "ALL")
UNAVAILABLE_ERRORS = (NoHostAvailable, DriverException, RequestExecutionException)

QUERIES = {
    "put": "INSERT INTO records (record_type, id, version, body) VALUES (?, ?, ?, ?)",
    "get": "SELECT body FROM records WHERE record_type = ? AND id = ?",
    "list": "SELECT body FROM records WHERE record_type = ?",
    "delete": "DELETE FROM records WHERE record_type = ? AND id = ?",
}
PING_QUERY = "SELECT release_version FROM system.local"


class CassandraStore(RecordStore):
    """User records in Cassandra's records table, using prepared statements only.

    The table is created from schema/cassandra.cql, never by this code.
    Connects on first use, so the backend can start while Cassandra is down.
    """

    name = "cassandra"

    def __init__(
        self,
        hosts,
        port=9042,
        keyspace="app",
        local_dc="dc1",
        consistency="QUORUM",
        username=None,
        password=None,
        timeout_seconds=2.0,
    ):
        if not hosts:
            raise ValueError("at least one Cassandra host is required")
        for host in hosts:
            require_str("host", host)
        require_str("keyspace", keyspace)
        if not KEYSPACE_PATTERN.match(keyspace):
            raise ValueError(f"invalid Cassandra keyspace name: {keyspace!r}")
        require_str("local_dc", local_dc)
        require_choice("consistency", consistency, CONSISTENCY_LEVELS)
        self._hosts = list(hosts)
        self._port = port
        self._keyspace = keyspace
        self._local_dc = local_dc
        self._consistency = getattr(ConsistencyLevel, consistency)
        self._auth = PlainTextAuthProvider(username, password) if username else None
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._cluster = None
        self._session = None
        self._statements = None

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        body = json.dumps(record, allow_nan=False)
        self._execute("put", (record_type, record["id"], record["version"], body))

    def get(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        row = self._execute("get", (record_type, record_id)).one()
        return json.loads(row.body) if row is not None else None

    def list(self, record_type):
        require_record_type(record_type)
        rows = self._execute("list", (record_type,))
        try:
            return [json.loads(row.body) for row in rows]
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def delete(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        self._execute("delete", (record_type, record_id))

    def ping(self):
        started = time.perf_counter()
        self._execute("ping", ())
        return (time.perf_counter() - started) * 1000

    def close(self):
        with self._lock:
            if self._cluster is not None:
                self._cluster.shutdown()
            self._cluster = None
            self._session = None
            self._statements = None

    def _execute(self, query_name, params):
        session, statements = self._connect()
        try:
            return session.execute(statements[query_name], params)
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def _connect(self):
        with self._lock:
            if self._session is not None:
                return self._session, self._statements
            profile = ExecutionProfile(
                load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy(local_dc=self._local_dc)),
                consistency_level=self._consistency,
                request_timeout=self._timeout,
            )
            cluster = Cluster(
                contact_points=self._hosts,
                port=self._port,
                auth_provider=self._auth,
                connect_timeout=self._timeout,
                execution_profiles={EXEC_PROFILE_DEFAULT: profile},
            )
            try:
                session = cluster.connect(self._keyspace)
                statements = self._prepare(session)
            except UNAVAILABLE_ERRORS as error:
                cluster.shutdown()
                raise StoreUnavailable(self.name, str(error)) from error
            except Exception:
                cluster.shutdown()
                raise
            self._cluster = cluster
            self._session = session
            self._statements = statements
            return session, statements

    def _prepare(self, session):
        statements = {query_name: session.prepare(query) for query_name, query in QUERIES.items()}
        ping = session.prepare(PING_QUERY)
        ping.consistency_level = ConsistencyLevel.ONE
        statements["ping"] = ping
        return statements