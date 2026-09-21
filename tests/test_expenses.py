import datetime

from tests.conftest import make_expense


class TestCreate:
    def test_create_minimal(self, client):
        resp = make_expense(client, 12.5, "groceries")
        data = resp.json()
        assert data["amount"] == 12.5
        assert data["category"] == "Groceries"  # normalized: first char uppercased
        assert data["note"] == ""
        assert data["date"] == datetime.date.today().isoformat()
        assert data["id"] > 0
        assert "created_at" in data

    def test_create_full(self, client):
        resp = make_expense(client, 1234.56, "travel", note="flight", date="2026-09-10")
        data = resp.json()
        assert data["amount"] == 1234.56
        assert data["note"] == "flight"
        assert data["date"] == "2026-09-10"

    def test_amount_rounded_to_cents(self, client):
        data = make_expense(client, 10.005, "misc").json()
        assert data["amount"] == 10.01

    def test_category_whitespace_stripped(self, client):
        data = make_expense(client, 5, "   dining out   ").json()
        assert data["category"] == "Dining out"

    def test_integer_amount(self, client):
        data = make_expense(client, 40, "rent").json()
        assert data["amount"] == 40.0


class TestValidation:
    def test_zero_amount_rejected(self, client):
        make_expense(client, 0, "misc", expect=422)

    def test_negative_amount_rejected(self, client):
        make_expense(client, -5, "misc", expect=422)

    def test_non_numeric_amount_rejected(self, client):
        resp = client.post("/expenses", json={"amount": "abc", "category": "x"})
        assert resp.status_code == 422

    def test_missing_category_rejected(self, client):
        resp = client.post("/expenses", json={"amount": 5})
        assert resp.status_code == 422

    def test_blank_category_rejected(self, client):
        make_expense(client, 5, "   ", expect=422)

    def test_category_too_long_rejected(self, client):
        make_expense(client, 5, "x" * 51, expect=422)

    def test_note_too_long_rejected(self, client):
        make_expense(client, 5, "cat", note="x" * 501, expect=422)

    def test_bad_date_rejected(self, client):
        make_expense(client, 5, "cat", date="2026-13-01", expect=422)

    def test_malformed_json_rejected(self, client):
        resp = client.post(
            "/expenses", content='{"amount": '[:20] + "not json", headers={
                "Content-Type": "application/json"
            }
        )
        assert resp.status_code == 422

    def test_unknown_fields_ignored(self, client):
        body = {"amount": 9.99, "category": "bills", "hacker": True}
        resp = client.post("/expenses", json=body)
        assert resp.status_code == 201


class TestList:
    def _seed(self, client):
        make_expense(client, 100, "rent", date="2026-08-05")
        make_expense(client, 50, "groceries", date="2026-09-01")
        make_expense(client, 30, "groceries", date="2026-09-15")

    def test_list_all_ordered(self, client):
        self._seed(client)
        data = client.get("/expenses").json()
        assert data["count"] == 3
        assert [e["date"] for e in data["expenses"]] == [
            "2026-09-15",
            "2026-09-01",
            "2026-08-05",
        ]

    def test_filter_by_category(self, client):
        self._seed(client)
        data = client.get("/expenses", params={"category": "groceries"}).json()
        assert data["count"] == 2
        assert all(e["category"] == "Groceries" for e in data["expenses"])

    def test_filter_category_case_insensitive(self, client):
        self._seed(client)
        data = client.get("/expenses", params={"category": "GROCERIES"}).json()
        assert data["count"] == 2

    def test_filter_by_date_range(self, client):
        self._seed(client)
        data = client.get(
            "/expenses", params={"start_date": "2026-09-01", "end_date": "2026-09-10"}
        ).json()
        assert data["count"] == 1
        assert data["expenses"][0]["category"] == "Groceries"

    def test_filter_start_only(self, client):
        self._seed(client)
        data = client.get("/expenses", params={"start_date": "2026-09-01"}).json()
        assert data["count"] == 2

    def test_empty_result(self, client):
        data = client.get("/expenses", params={"category": "nope"}).json()
        assert data == {"expenses": [], "count": 0}

    def test_invalid_date_rejected(self, client):
        resp = client.get("/expenses", params={"start_date": "not-a-date"})
        assert resp.status_code == 422

    def test_empty_db(self, client):
        assert client.get("/expenses").json() == {"expenses": [], "count": 0}