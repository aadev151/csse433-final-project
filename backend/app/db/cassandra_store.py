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