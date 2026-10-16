from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import conflict, install_error_handlers, not_found, store_down


class Body(BaseModel):
    name: str


def make_client():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/missing")
    def missing():
        raise not_found("signal", "abc")

    @app.get("/in-use")
    def in_use():
        raise conflict(
            "in_use",
            "Signal is used by experiments",
            used_by=[{"id": "e1", "name": "BTC sweep"}],
        )

    @app.get("/down")
    def down():
        raise store_down("cassandra_down", "Cassandra is unavailable")

    @app.post("/validate")
    def validate(body: Body):
        return body

    @app.get("/boom")
    def boom():
        raise RuntimeError("something broke")

    return TestClient(app, raise_server_exceptions=False)


def test_not_found_body():
    response = make_client().get("/missing")
    assert response.status_code == 404
    assert response.json() == {"reason": "not_found", "message": "signal abc was not found"}


def test_in_use_includes_used_by():
    response = make_client().get("/in-use")
    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == "in_use"
    assert body["used_by"] == [{"id": "e1", "name": "BTC sweep"}]


def test_used_by_omitted_when_not_set():
    response = make_client().get("/missing")
    assert "used_by" not in response.json()


def test_store_down():
    response = make_client().get("/down")
    assert response.status_code == 503
    assert response.json()["reason"] == "cassandra_down"


def test_validation_error_uses_contract_format():
    response = make_client().post("/validate", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["reason"] == "validation"
    assert "name" in body["message"]


def test_unexpected_error_is_500_in_contract_format():
    response = make_client().get("/boom")
    assert response.status_code == 500
    assert response.json() == {"reason": "internal", "message": "Unexpected server error"}