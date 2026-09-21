"""API routes: /expenses and /summary."""

from __future__ import annotations

import datetime
import sqlite3

from fastapi import APIRouter, HTTPException, Query, Request

from .auth import hash_password, verify_password
from .db import Database
from .models import (
    AuthCredentials,
    ExpenseCreate,
    ExpenseOut,
    amount_to_cents,
    normalize_category,
)

router = APIRouter()
public_router = APIRouter()


def _db(request: Request) -> Database:
    return request.app.state.db


def _user_id(request: Request) -> int | None:
    return getattr(request.state, "user_id", None)


def _auth(request: Request):
    return request.app.state.auth


def _month_bounds(month: str) -> tuple[str, str]:
    try:
        first = datetime.datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"month must be YYYY-MM, got {month!r}"
        )
    if first.month == 12:
        next_first = datetime.date(first.year + 1, 1, 1)
    else:
        next_first = datetime.date(first.year, first.month + 1, 1)
    return first.isoformat(), next_first.isoformat()


def _previous_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        year, mon = year - 1, 12
    else:
        mon -= 1
    return f"{year:04d}-{mon:02d}"


def _pct(current_cents: int, previous_cents: int) -> float | None:
    if previous_cents > 0:
        return round((current_cents - previous_cents) / previous_cents * 100, 2)
    return None


@public_router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@public_router.post("/auth/register", status_code=201)
def register(payload: AuthCredentials, request: Request) -> dict:
    auth = _auth(request)
    auth.require_jwt_configured()
    db = _db(request)
    password_salt, password_hash = hash_password(payload.password)
    try:
        user = db.create_user(payload.username, password_hash, password_salt)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username is already registered")
    return {
        "access_token": auth.create_access_token(user["id"], user["username"]),
        "token_type": "bearer",
        "user": {"id": user["id"], "username": user["username"]},
    }


@public_router.post("/auth/login")
def login(payload: AuthCredentials, request: Request) -> dict:
    auth = _auth(request)
    auth.require_jwt_configured()
    user = _db(request).get_user_by_username(payload.username)
    if user is None or not verify_password(
        payload.password, user["password_salt"], user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": auth.create_access_token(user["id"], user["username"]),
        "token_type": "bearer",
        "user": {"id": user["id"], "username": user["username"]},
    }


@router.post("/expenses", status_code=201)
def create_expense(payload: ExpenseCreate, request: Request) -> ExpenseOut:
    db = _db(request)
    when = payload.date or datetime.date.today()
    row = db.create_expense(
        amount_cents=amount_to_cents(payload.amount),
        category=payload.category,
        note=payload.note,
        date=when.isoformat(),
        user_id=_user_id(request),
    )
    return ExpenseOut.from_row(row)


@router.get("/expenses")
def list_expenses(
    request: Request,
    category: str | None = None,
    start_date: datetime.date | None = Query(
        default=None, description="Inclusive, ISO YYYY-MM-DD"
    ),
    end_date: datetime.date | None = Query(
        default=None, description="Inclusive, ISO YYYY-MM-DD"
    ),
) -> dict:
    db = _db(request)
    cleaned = None
    if category is not None and category.strip():
        cleaned = normalize_category(category)
    rows = db.list_expenses(
        category=cleaned,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        user_id=_user_id(request),
    )
    expenses = [ExpenseOut.from_row(r) for r in rows]
    return {"expenses": expenses, "count": len(expenses)}


@router.get("/summary")
def summary(
    request: Request,
    month: str | None = Query(
        default=None, description="Reference month YYYY-MM; defaults to now"
    ),
) -> dict:
    db = _db(request)
    ref = month or datetime.date.today().strftime("%Y-%m")
    cur_start, cur_end = _month_bounds(ref)
    prev = _previous_month(ref)
    prev_start, prev_end = _month_bounds(prev)

    user_id = _user_id(request)
    cur_total = db.month_total(cur_start, cur_end, user_id=user_id)
    prev_total = db.month_total(prev_start, prev_end, user_id=user_id)
    change_pct = _pct(cur_total, prev_total)
    prev_exists = prev_total > 0

    cur_cats = {
        r["category"]: r["amount_cents"]
        for r in db.month_category_totals(cur_start, cur_end, user_id=user_id)
    }
    prev_cats = {
        r["category"]: r["amount_cents"]
        for r in db.month_category_totals(prev_start, prev_end, user_id=user_id)
    }

    by_category = []
    for cat in sorted(set(cur_cats) | set(prev_cats)):
        cur_amt = cur_cats.get(cat, 0)
        prev_amt = prev_cats.get(cat, 0)
        pct = _pct(cur_amt, prev_amt)
        by_category.append(
            {
                "category": cat,
                "amount": round(cur_amt / 100, 2),
                "previous_amount": round(prev_amt / 100, 2),
                "change_pct": pct,
                "flagged": pct is not None and pct > 20,
            }
        )
    by_category.sort(key=lambda c: c["amount"], reverse=True)

    flagged = [c["category"] for c in by_category if c["flagged"]]

    insight = None
    if prev_exists and change_pct is not None:
        direction = "up" if change_pct >= 0 else "down"
        insight = (
            f"Spend {direction} {abs(change_pct):.2f}% "
            f"vs previous month ({prev})"
        )
    if flagged:
        word = "category" if len(flagged) == 1 else "categories"
        insight = (
            f"{len(flagged)} {word} up more than 20% vs previous month: "
            f"{', '.join(flagged)}"
        )

    return {
        "total_spend": round(db.total_all(user_id=user_id) / 100, 2),
        "total_expenses": db.count_all(user_id=user_id),
        "all_time_spend_by_category": [
            {"category": r["category"], "amount": round(r["amount_cents"] / 100, 2)}
            for r in db.category_totals_all(user_id=user_id)
        ],
        "month_over_month": {
            "current_month": ref,
            "current_total": round(cur_total / 100, 2),
            "previous_month": prev,
            "previous_total": round(prev_total / 100, 2),
            "change_pct": change_pct,
            "previous_exists": prev_exists,
            "insight": insight,
        },
        "spend_by_category": by_category,
    }
