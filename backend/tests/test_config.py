import pytest

from app.config import load_settings


def test_defaults_to_memory_mode():
    settings = load_settings({})
    assert settings.store_mode == "memory"
    assert settings.frontend_origins == ("http://localhost:5173",)


def test_real_mode_requires_connection_settings():
    with pytest.raises(ValueError) as error:
        load_settings({"STORE_MODE": "real"})
    message = str(error.value)
    assert "MONGO_URI" in message
    assert "CASSANDRA_HOSTS" in message
    assert "REDIS_URL or REDIS_SENTINELS" in message


def test_real_mode_with_all_settings():
    settings = load_settings(
        {
            "STORE_MODE": "real",
            "MONGO_URI": "mongodb://127.0.0.1:27017",
            "CASSANDRA_HOSTS": "10.0.0.11, 10.0.0.12",
            "REDIS_SENTINELS": "host-a:26379,host-b",
        }
    )
    assert settings.cassandra_hosts == ("10.0.0.11", "10.0.0.12")
    assert settings.redis_sentinels == (("host-a", 26379), ("host-b", 26379))


def test_rejects_unknown_store_mode():
    with pytest.raises(ValueError):
        load_settings({"STORE_MODE": "postgres"})


def test_rejects_unknown_consistency():
    with pytest.raises(ValueError):
        load_settings({"CASSANDRA_CONSISTENCY": "SOME"})


def test_consistency_is_case_insensitive():
    assert load_settings({"CASSANDRA_CONSISTENCY": "quorum"}).cassandra_consistency == "QUORUM"