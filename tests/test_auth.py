class TestAuthDisabled:
    def test_no_key_required_when_unconfigured(self, client):
        assert client.get("/expenses").status_code == 200
        assert client.get("/summary").status_code == 200

    def test_post_works_without_key(self, client):
        resp = client.post("/expenses", json={"amount": 10, "category": "test"})
        assert resp.status_code == 201


class TestAuthEnabled:
    def test_missing_key_rejected(self, authed_client):
        assert authed_client.get("/expenses").status_code == 401
        assert authed_client.get("/summary").status_code == 401
        assert authed_client.post(
            "/expenses", json={"amount": 10, "category": "test"}
        ).status_code == 401

    def test_wrong_key_rejected(self, authed_client):
        resp = authed_client.get("/expenses", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_case_sensitive_key(self, authed_client):
        resp = authed_client.get(
            "/expenses", headers={"X-API-Key": "SECRET-KEY-123"}
        )
        assert resp.status_code == 401

    def test_401_detail(self, authed_client):
        resp = authed_client.get("/expenses")
        assert resp.json()["detail"] == "Invalid or missing API key"

    def test_correct_key_allowed(self, authed_client):
        assert (
            authed_client.get(
                "/expenses", headers={"X-API-Key": "secret-key-123"}
            ).status_code
            == 200
        )

    def test_correct_key_can_create_and_list(self, authed_client):
        headers = {"X-API-Key": "secret-key-123"}
        assert (
            authed_client.post(
                "/expenses", json={"amount": 20, "category": "rent"}, headers=headers
            ).status_code
            == 201
        )
        data = authed_client.get("/expenses", headers=headers).json()
        assert data["count"] == 1

    def test_health_endpoint_exempt(self, authed_client):
        assert authed_client.get("/health").status_code == 200