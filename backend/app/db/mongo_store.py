from pymongo import MongoClient
from pymongo.errors import PyMongoError
from app.records.checks import require_record, require_record_type, require_str
from app.records.stores import RecordStore, StoreUnavailable

class MongoStore(RecordStore):

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

    def get(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        collection = self._db[record_type]
        filter_by_id = {"_id": record_id}
        exclude_internal_id = {"_id": False}
        try:
            return collection.find_one(filter_by_id, exclude_internal_id)
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def list(self, record_type):
        require_record_type(record_type)
        collection = self._db[record_type]
        no_filter = {}
        excluded_internal_id = {"_id": False}
        try:
            all_documents = collection.find(no_filter, excluded_internal_id)
            return list(all_documents)
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def delete(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        collection = self._db[record_type]
        filter_by_id = {"_id": record_id}
        try:
            collection.delete_one(filter_by_id)
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def close(self):
        self._client.close()

