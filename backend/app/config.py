import os
from dataclasses import dataclass
from typing import Optional

STORE_MODES = ("memory", "real")
CONSISTENCY_LEVELS = ("ONE", "TWO", "QUORUM", "LOCAL_QUORUM", "ALL")


@dataclass(frozen=True)
class Settings:
    store_mode: str = "memory"
    data_dir: str = "data"
    frontend_origins: tuple = ("http://localhost:5173",)
    store_timeout_seconds: float = 2.0
    mongo_uri: Optional[str] = None
    mongo_db: str = "app"
    cassandra_hosts: tuple = ()
    cassandra_port: int = 9042
    cassandra_keyspace: str = "app"
    cassandra_local_dc: str = "dc1"
    cassandra_consistency: str = "QUORUM"
    cassandra_username: Optional[str] = None
    cassandra_password: Optional[str] = None
    redis_url: Optional[str] = None
    redis_sentinels: tuple = ()
    redis_master_name: str = "mymaster"
    redis_password: Optional[str] = None


def _split(value):
    return tuple(part.strip() for part in (value or "").split(",") if part.strip())


def _host_port(text, default_port):
    host, separator, port = text.rpartition(":")
    if not separator:
        return text, default_port
    return host, int(port)


def load_settings(env=None):
    env = os.environ if env is None else env

    def get(name, default=None):
        value = env.get(name)
        return value if value not in (None, "") else default

    settings = Settings(
        store_mode=get("STORE_MODE", "memory"),
        data_dir=get("DATA_DIR", "data"),
        frontend_origins=_split(get("FRONTEND_ORIGINS", "http://localhost:5173")),
        store_timeout_seconds=float(get("STORE_TIMEOUT_SECONDS", "2")),
        mongo_uri=get("MONGO_URI"),
        mongo_db=get("MONGO_DB", "app"),
        cassandra_hosts=_split(get("CASSANDRA_HOSTS")),
        cassandra_port=int(get("CASSANDRA_PORT", "9042")),
        cassandra_keyspace=get("CASSANDRA_KEYSPACE", "app"),
        cassandra_local_dc=get("CASSANDRA_LOCAL_DC", "dc1"),
        cassandra_consistency=get("CASSANDRA_CONSISTENCY", "QUORUM").upper(),
        cassandra_username=get("CASSANDRA_USERNAME"),
        cassandra_password=get("CASSANDRA_PASSWORD"),
        redis_url=get("REDIS_URL"),
        redis_sentinels=tuple(_host_port(item, 26379) for item in _split(get("REDIS_SENTINELS"))),
        redis_master_name=get("REDIS_MASTER_NAME", "mymaster"),
        redis_password=get("REDIS_PASSWORD"),
    )
    _validate(settings)
    return settings


def _validate(settings):
    if settings.store_mode not in STORE_MODES:
        raise ValueError(f"STORE_MODE must be one of {list(STORE_MODES)}, got {settings.store_mode!r}")
    if settings.cassandra_consistency not in CONSISTENCY_LEVELS:
        raise ValueError(
            f"CASSANDRA_CONSISTENCY must be one of {list(CONSISTENCY_LEVELS)}, "
            f"got {settings.cassandra_consistency!r}"
        )
    if settings.store_timeout_seconds <= 0:
        raise ValueError("STORE_TIMEOUT_SECONDS must be greater than 0")
    if settings.store_mode == "real":
        missing = []
        if not settings.mongo_uri:
            missing.append("MONGO_URI")
        if not settings.cassandra_hosts:
            missing.append("CASSANDRA_HOSTS")
        if not settings.redis_url and not settings.redis_sentinels:
            missing.append("REDIS_URL or REDIS_SENTINELS")
        if missing:
            raise ValueError(f"STORE_MODE=real needs these settings: {', '.join(missing)}")