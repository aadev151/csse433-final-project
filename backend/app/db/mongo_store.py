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

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        record_id = record["id"]
        document = {**record, "_id": record_id}
        collection = self._db[record_type]
        filter_by_id = {"_id": record_id}
        try:
            collection.replace_one(filter_by_id, document, upsert=True)
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error
