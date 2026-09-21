"""Entrypoint for `uvicorn run:app` and `python run.py`."""

from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

from app.main import create_app

load_dotenv()


def get_app():
    expire_minutes = int(
        os.environ.get("SPEND_TRACKER_JWT_EXPIRE_MINUTES", "1440")
    )
    cors_origins = [
        origin.strip()
        for origin in os.environ.get(
            "SPEND_TRACKER_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    return create_app(
        db_path=os.environ.get("SPEND_TRACKER_DB_PATH", "data/spend.db"),
        api_key=os.environ.get("SPEND_TRACKER_API_KEY") or None,
        jwt_secret=os.environ.get("SPEND_TRACKER_JWT_SECRET") or None,
        jwt_expire_minutes=expire_minutes,
        cors_origins=cors_origins,
    )


app = get_app()


if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=True)
