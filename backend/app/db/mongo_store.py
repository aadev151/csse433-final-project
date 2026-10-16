import re
import time

from pymongo import MongoClient, ReadPreference
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

from app.records.checks import require_record, require_record_type, require_str
from app.records.stores import RecordStore, StoreUnavailable

DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


class MongoStore(RecordStore):
    """User records in MongoDB: one collection per record type, _id = record id."""

    name = "mongodb"

    def __init__(self, client, database_name="app", timeout_ms=2000):
        require_str("database_name", database_name)
        if not DATABASE_NAME_PATTERN.match(database_name):
            raise ValueError(f"invalid MongoDB database name: {database_name!r}")
        self._client = client
        self._db = client.get_database(
            database_name,
            write_concern=WriteConcern(w="majority", wtimeout=timeout_ms),
            read_preference=ReadPreference.PRIMARY_PREFERRED,
        )

    @classmethod
    def connect(cls, uri, database_name="app", timeout_ms=2000):
        require_str("uri", uri)
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        return cls(client, database_name=database_name, timeout_ms=timeout_ms)

    def put(self, record_type, record):
        require_record_type(record_type)
        require_record(record)
        document = {**record, "_id": record["id"]}
        try:
            self._db[record_type].replace_one({"_id": record["id"]}, document, upsert=True)
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def get(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        try:
            return self._db[record_type].find_one({"_id": record_id}, {"_id": 0})
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def list(self, record_type):
        require_record_type(record_type)
        try:
            return list(self._db[record_type].find({}, {"_id": 0}))
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def delete(self, record_type, record_id):
        require_record_type(record_type)
        require_str("record_id", record_id)
        try:
            self._db[record_type].delete_one({"_id": record_id})
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error

    def ping(self):
        started = time.perf_counter()
        try:
            self._client.admin.command("ping")
        except PyMongoError as error:
            raise StoreUnavailable(self.name, str(error)) from error
        return (time.perf_counter() - started) * 1000

    def close(self):
        self._client.close()