from pymongo import MongoClient
from pymongo.errors import PyMongoError
from app.records.checks import require_record, require_record_type, require_str
from app.records.stores import RecordStore, StoreUnavailable

class MongoDB(RecordStore):

    name = "mongodb"

    def __init__(self, uri, database_name="app", timeout_ms=2000):
        require_str("uri", uri)
        require_str("database_name", database_name)
        self._client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        self._db = self._client[database_name]
