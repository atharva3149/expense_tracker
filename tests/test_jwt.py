from fastapi.testclient import TestClient

from app.main import create_app


def make_jwt_client(tmp_path):
    app = create_app(
        db_path=str(tmp_path / "jwt.db"),
        jwt_secret="unit-test-secret-that-is-long-enough",
        serve_static=False,
    )
    return TestClient(app)


def register(client, username="alice", password="correct-horse"):
    response = client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


class TestJwtAuth:
    def test_register_and_login_return_bearer_token(self, tmp_path):
        with make_jwt_client(tmp_path) as client:
            data, _ = register(client, username=" Alice ")
            assert data["token_type"] == "bearer"
            assert data["user"]["username"] == "alice"

            response = client.post(
                "/auth/login",
                json={"username": "ALICE", "password": "correct-horse"},
            )
            assert response.status_code == 200
            assert response.json()["access_token"]

    def test_duplicate_and_invalid_login_are_rejected(self, tmp_path):
        with make_jwt_client(tmp_path) as client:
            register(client)
            duplicate = client.post(
                "/auth/register",
                json={"username": "alice", "password": "another-pass"},
            )
            assert duplicate.status_code == 409

            invalid = client.post(
                "/auth/login",
                json={"username": "alice", "password": "wrong-pass"},
            )
            assert invalid.status_code == 401

    def test_protected_routes_require_a_valid_token(self, tmp_path):
        with make_jwt_client(tmp_path) as client:
            assert client.get("/expenses").status_code == 401
            assert client.get(
                "/expenses", headers={"Authorization": "Bearer not-a-token"}
            ).status_code == 401

    def test_expenses_are_isolated_per_user(self, tmp_path):
        with make_jwt_client(tmp_path) as client:
            _, alice_headers = register(client, username="alice")
            _, bob_headers = register(client, username="bob")

            created = client.post(
                "/expenses",
                json={"amount": 25, "category": "lunch"},
                headers=alice_headers,
            )
            assert created.status_code == 201

            alice_expenses = client.get("/expenses", headers=alice_headers)
            bob_expenses = client.get("/expenses", headers=bob_headers)
            assert alice_expenses.json()["count"] == 1
            assert bob_expenses.json()["count"] == 0
            assert client.get("/summary", headers=bob_headers).json()[
                "total_spend"
            ] == 0

    def test_register_requires_jwt_configuration(self, tmp_path):
        app = create_app(db_path=str(tmp_path / "no-jwt.db"), serve_static=False)
        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={"username": "alice", "password": "correct-horse"},
            )
            assert response.status_code == 503
