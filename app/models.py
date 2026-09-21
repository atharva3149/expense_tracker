"""Pydantic request/response models and money helpers.

Money is accepted as a decimal amount in currency units and converted to
integer cents for storage, avoiding float rounding errors.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, Field, field_validator

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_category(value: str) -> str:
    value = value.strip()
    return value[0].upper() + value[1:] if value else value


def amount_to_cents(amount: Decimal) -> int:
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(rounded * 100)


def cents_to_amount(cents: int) -> float:
    return round(cents / 100, 2)


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(gt=0, description="Amount in currency units, e.g. 1234.56")
    category: str = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=500)
    date: datetime.date | None = Field(
        default=None, description="ISO date, defaults to today"
    )

    @field_validator("category", mode="before")
    @classmethod
    def _clean_category(cls, value):
        if isinstance(value, str):
            return normalize_category(value)
        return value

    @field_validator("note", mode="before")
    @classmethod
    def _clean_note(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class ExpenseOut(BaseModel):
    id: int
    amount: float
    category: str
    note: str
    date: datetime.date
    created_at: str

    @classmethod
    def from_row(cls, row) -> "ExpenseOut":
        return cls(
            id=row["id"],
            amount=cents_to_amount(row["amount_cents"]),
            category=row["category"],
            note=row["note"],
            date=datetime.datetime.strptime(row["date"], "%Y-%m-%d").date(),
            created_at=row["created_at"],
        )


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def _clean_username(cls, value):
        if not isinstance(value, str):
            return value
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value):
        if not isinstance(value, str):
            return value

        letter_count = len(re.findall(r"[A-Za-z]", value))
        if letter_count < 6:
            raise ValueError("Password must contain at least 6 alphabetic characters")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("Password must contain at least one special character")
        return value
