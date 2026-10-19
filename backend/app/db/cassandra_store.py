import json
import threading
import time

from cassandra import ConsistencyLevel, DriverException, RequestExecutionException
from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile, NoHostAvailable
from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy

from app.records.checks import require_record, require_record_type, require_str
from app.records.stores import RecordStore, StoreUnavailable

UNAVAILABLE_ERRORS = (NoHostAvailable, DriverException, RequestExecutionException)

QUERIES = {
    "put": "INSERT INTO records (record_type, id, version, body) VALUES (?, ?, ?, ?)",
    "get": "SELECT body FROM records WHERE record_type = ? AND id = ?",
    "list": "SELECT body FROM records WHERE record_type = ?",
    "delete": "DELETE FROM records WHERE record_type = ? AND id = ?",
}

PING_QUERY = "SELECT release_version FROM system.local"


class CassandraStore(RecordStore):

    name = "cassandra"

    def __init__(self, hosts, port=9042, keyspace="app", local_dc="dc1", consistency="QUORUM", timeout_seconds=2.0):
        require_str("keyspace", keyspace)
        require_str("local_dc", local_dc)
        self._hosts = list(hosts)
        self._port = port
        self._keyspace = keyspace
        self._local_dc = local_dc
        self._consistency = getattr(ConsistencyLevel, consistency)
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._cluster = None
        self._session = None
        self._statements = None

    def _connect(self):
        with self._lock:
            if self._session is not None:
                return self._session, self._statements

            dc_policy = DCAwareRoundRobinPolicy(local_dc=self._local_dc)
            token_policy = TokenAwarePolicy(dc_policy)
            profile = ExecutionProfile(
                load_balancing_policy=token_policy,
                consistency_level=self._consistency,
                request_timeout=self._timeout,
            )
            profiles = {EXEC_PROFILE_DEFAULT: profile}
            cluster = Cluster(
                contact_points=self._hosts,
                port=self._port,
                connect_timeout=self._timeout,
                execution_profiles=profiles,
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
        statements = {}
        for query_name, query_text in QUERIES.items():
            prepared = session.prepare(query_text)
            statements[query_name] = prepared
        ping_statement = session.prepare(PING_QUERY)
        ping_statement.consistency_level = ConsistencyLevel.ONE
        statements["ping"] = ping_statement
        return statements

    def _execute(self, query_name, params):
        session, statements = self._connect()
        statement = statements[query_name]
        try:
            result = session.execute(statement, params)
            return result
        except UNAVAILABLE_ERRORS as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        record_id = record["id"]
        version = record["version"]
        body = json.dumps(record, allow_nan = False)
        params = (record_type, record_id, version, body)
        self._execute("put", params)