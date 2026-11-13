import pytest

from app.records.checks import (
    require_choice,
    require_int,
    require_record,
    require_record_type,
    require_store,
    require_str,
)


def test_require_str_accepts_string():
    assert require_str("name", "abc") == "abc"


@pytest.mark.parametrize("value", [1, None, 3.5, b"abc", ["abc"]])
def test_require_str_rejects_non_string(value):
    with pytest.raises(TypeError):
        require_str("name", value)


@pytest.mark.parametrize("value", ["", "   "])
def test_require_str_rejects_empty(value):
    with pytest.raises(ValueError):
        require_str("name", value)


def test_require_int_accepts_int():
    assert require_int("n", 5) == 5


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None])
def test_require_int_rejects_non_int_including_bool(value):
    with pytest.raises(TypeError):
        require_int("n", value)


def test_require_int_enforces_minimum():
    with pytest.raises(ValueError):
        require_int("n", 0, minimum=1)


def test_require_choice_rejects_value_not_in_choices():
    with pytest.raises(ValueError):
        require_choice("op", "upsert", ("put", "delete"))


def test_require_store_and_record_type():
    assert require_store("cassandra") == "cassandra"
    assert require_record_type("signal") == "signal"
    with pytest.raises(ValueError):
        require_store("postgres")
    with pytest.raises(ValueError):
        require_record_type("users")


def test_require_record_accepts_valid_record():
    record = {"id": "s1", "version": 1, "params": {"field": "qty"}}
    assert require_record(record, record_id="s1") is record


@pytest.mark.parametrize("value", ["not a dict", ["id", "version"], None])
def test_require_record_rejects_non_dict(value):
    with pytest.raises(TypeError):
        require_record(value)


@pytest.mark.parametrize("record", [{"version": 1}, {"id": "s1"}])
def test_require_record_rejects_missing_fields(record):
    with pytest.raises(ValueError):
        require_record(record)


def test_require_record_rejects_wrong_field_types():
    with pytest.raises(TypeError):
        require_record({"id": 1, "version": 1})
    with pytest.raises(TypeError):
        require_record({"id": "s1", "version": "1"})
    with pytest.raises(TypeError):
        require_record({"id": "s1", "version": True})


def test_require_record_rejects_version_below_one():
    with pytest.raises(ValueError):
        require_record({"id": "s1", "version": 0})


def test_require_record_rejects_id_mismatch():
    with pytest.raises(ValueError):
        require_record({"id": "s1", "version": 1}, record_id="s2")


@pytest.mark.parametrize("bad_value", [{1, 2}, float("nan"), object()])
def test_require_record_rejects_non_json_values(bad_value):
    with pytest.raises(ValueError):
        require_record({"id": "s1", "version": 1, "bad": bad_value})