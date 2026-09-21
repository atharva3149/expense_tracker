import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "spend.db"))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed_client(tmp_path):
    app = create_app(db_path=str(tmp_path / "spend.db"), api_key="secret-key-123")
    with TestClient(app) as c:
        yield c


def make_expense(client, amount, category, note="", date=None, expect=201):
    body = {"amount": amount, "category": category}
    if note:
        body["note"] = note
    if date:
        body["date"] = date
    resp = client.post("/expenses", json=body)
    assert resp.status_code == expect, resp.text
    return resp