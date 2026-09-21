from tests.conftest import make_expense


class TestSummaryMath:
    def test_empty_db(self, client):
        s = client.get("/summary").json()
        assert s["total_spend"] == 0
        assert s["total_expenses"] == 0
        assert s["spend_by_category"] == []
        m = s["month_over_month"]
        assert m["current_total"] == 0
        assert m["previous_total"] == 0
        assert m["change_pct"] is None
        assert m["previous_exists"] is False

    def test_single_month(self, client):
        make_expense(client, 100, "rent", date="2026-09-01")
        make_expense(client, 50.5, "groceries", date="2026-09-10")
        s = client.get("/summary", params={"month": "2026-09"}).json()
        assert s["total_spend"] == 150.5
        assert s["total_expenses"] == 2
        all_cat = {c["category"]: c["amount"] for c in s["all_time_spend_by_category"]}
        assert all_cat == {"Rent": 100.0, "Groceries": 50.5}
        m = s["month_over_month"]
        assert m["current_total"] == 150.5
        assert m["previous_total"] == 0
        assert m["change_pct"] is None
        assert m["previous_exists"] is False
        assert m["insight"] is None

    def test_mom_change_down(self, client):
        make_expense(client, 500, "groceries", date="2026-08-01")
        make_expense(client, 500, "groceries", date="2026-08-02")
        make_expense(client, 200, "travel", date="2026-08-15")
        make_expense(client, 600, "groceries", date="2026-09-01")
        make_expense(client, 300, "travel", date="2026-09-05")

        s = client.get("/summary", params={"month": "2026-09"}).json()
        m = s["month_over_month"]
        assert m["current_total"] == 900
        assert m["previous_total"] == 1200
        assert m["change_pct"] == round((900 - 1200) / 1200 * 100, 2) == -25.0
        assert m["previous_exists"] is True

        by = {c["category"]: c for c in s["spend_by_category"]}
        assert by["Groceries"]["change_pct"] == -40.0
        assert by["Groceries"]["flagged"] is False
        assert by["Travel"]["change_pct"] == 50.0
        assert by["Travel"]["flagged"] is True
        assert "Travel" in m["insight"]

    def test_category_disappeared_from_previous_month(self, client):
        make_expense(client, 100, "oldcat", date="2026-08-01")
        make_expense(client, 50, "newcat", date="2026-09-01")
        s = client.get("/summary", params={"month": "2026-09"}).json()
        by = {c["category"]: c for c in s["spend_by_category"]}
        assert by["Oldcat"]["amount"] == 0
        assert by["Oldcat"]["change_pct"] == -100.0
        assert by["Newcat"]["previous_amount"] == 0
        assert by["Newcat"]["change_pct"] is None
        assert by["Newcat"]["flagged"] is False

    def test_flag_boundary_exactly_20_percent_not_flagged(self, client):
        make_expense(client, 500, "groceries", date="2026-08-01")
        make_expense(client, 600, "groceries", date="2026-09-01")
        s = client.get("/summary", params={"month": "2026-09"}).json()
        assert s["spend_by_category"][0]["change_pct"] == 20.0
        assert s["spend_by_category"][0]["flagged"] is False
        assert s["month_over_month"]["insight"] is not None  # aggregate insight only

    def test_flag_just_over_20_percent_flagged(self, client):
        make_expense(client, 500, "groceries", date="2026-08-01")
        make_expense(client, 601, "groceries", date="2026-09-01")
        s = client.get("/summary", params={"month": "2026-09"}).json()
        cat = s["spend_by_category"][0]
        assert cat["change_pct"] == 20.2
        assert cat["flagged"] is True
        assert "Groceries" in s["month_over_month"]["insight"]

    def test_default_month_is_current(self, client):
        make_expense(client, 10, "coffee")
        s = client.get("/summary").json()
        assert s["month_over_month"]["current_total"] == 10
        assert s["spend_by_category"][0]["category"] == "Coffee"


class TestSummaryValidation:
    def test_bad_month_rejected(self, client):
        assert client.get("/summary", params={"month": "2026/09"}).status_code == 422
        assert client.get("/summary", params={"month": "2026"}).status_code == 422
        assert client.get("/summary", params={"month": "2026-09-01"}).status_code == 422

    def test_january_rolls_previous_month_to_december(self, client):
        make_expense(client, 10, "deco", date="2025-12-31")
        make_expense(client, 25, "deco", date="2026-01-01")
        s = client.get("/summary", params={"month": "2026-01"}).json()
        m = s["month_over_month"]
        assert m["previous_month"] == "2025-12"
        assert m["previous_total"] == 10
        assert m["change_pct"] == 150.0