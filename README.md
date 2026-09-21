# Spend Tracker

A small expense-logging service with a FastAPI REST API, durable SQLite
storage, JWT authentication, and a React frontend. Users can record expenses,
filter them by category/date, and view all-time and month-over-month summaries.

## Quick Start

```bash
# from the project root
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

For the React development server, use a second terminal:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open <http://localhost:5173/> for the React UI, or
<http://127.0.0.1:8000/docs> for the API docs. The Vite proxy forwards API
requests to FastAPI. For a single-server deployment, build the frontend:

```bash
cd frontend
npm run build
```

FastAPI serves the built React files from `frontend/dist` when that directory
exists. The source-only development workflow uses Vite directly.

Run the backend tests with:

```bash
python -m pytest -q
```

## Environment

Copy the root `.env.example` to `.env` and replace the JWT secret with a long
random value. Copy `frontend/.env.example` to `frontend/.env` for frontend-only
settings. Both `.env` files are ignored by git.

### Backend `.env`

| Variable | Default | Purpose |
| --- | --- | --- |
| `SPEND_TRACKER_DB_PATH` | `data/spend.db` | SQLite file location. |
| `SPEND_TRACKER_JWT_SECRET` | unset | Enables registration/login and Bearer-token auth. |
| `SPEND_TRACKER_JWT_EXPIRE_MINUTES` | `1440` | JWT lifetime. |
| `SPEND_TRACKER_CORS_ORIGINS` | Vite localhost origins | Comma-separated browser origins. |
| `SPEND_TRACKER_API_KEY` | unset | Optional legacy `X-API-Key` authentication. |

`python-dotenv` loads `.env` when the service starts through `run.py`.

### Frontend `frontend/.env`

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_URL` | empty | API URL; empty uses the Vite proxy or same origin. |
| `VITE_CURRENCY` | `USD` | Currency code displayed by React. |

## Authentication

JWT is the recommended authentication mode for the React client. Set
`SPEND_TRACKER_JWT_SECRET` to enable these public endpoints:

### `POST /auth/register`

```json
{ "username": "alex", "password": "Abcdefg1!" }
```

The password must include:
- at least one special character
- at least one number
- at least 6 alphabetic characters
- at least one letter overall

Example valid password: `P@ssw0rd`

Returns `201` with an access token and user object. Usernames are normalized to
lowercase, and duplicate usernames return `409`.

### `POST /auth/login`

Accepts the same body and returns:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user": { "id": 1, "username": "alex" }
}
```

Send the token to protected routes with:

```text
Authorization: Bearer <access_token>
```

Passwords are stored as salted scrypt hashes. Every JWT-authenticated expense
and summary query is scoped to the token's user id. `/health`, registration,
and login remain public. Without a JWT secret, the existing keyless local API
behavior remains available; registration/login return `503`.

The optional legacy mode can be enabled with `SPEND_TRACKER_API_KEY=secret` and
uses `X-API-Key: secret`. It represents one shared namespace and is intended
for scripts, not the React UI.

## API

Money is accepted and returned in currency units, such as `42.50`, but stored
as integer cents to avoid float rounding errors. Dates use ISO `YYYY-MM-DD`.

### `POST /expenses`

```json
{
  "amount": 42.50,
  "category": "Groceries",
  "note": "weekly shop",
  "date": "2026-09-05"
}
```

`category` is required and limited to 50 characters. It is trimmed and its
first character is uppercased. `note` is optional and limited to 500
characters. `date` defaults to today. Invalid input returns `422`.

### `GET /expenses`

Optional query parameters are `category` (case-insensitive), `start_date`, and
`end_date` (both inclusive). The response is sorted newest first:

```json
{ "expenses": [], "count": 0 }
```

### `GET /summary`

Optional `month=YYYY-MM` selects the reference month; it defaults to the
server's current month. The response contains `total_spend`,
`total_expenses`, all-time category totals, current/previous month totals, the
percentage change, and a current-month category breakdown. A category is
`flagged` when its spend increased by more than 20% versus the previous month.

### `GET /health`

Unauthenticated liveness probe returning `{ "status": "ok" }`.

## Design Decisions

- **Integer cents:** decimal input is quantized with `ROUND_HALF_UP` before it
  reaches SQLite, so totals do not accumulate binary float drift.
- **SQLite with a real schema:** the database has `users` and `expenses` tables,
  checks, indexes, and a small migration for adding `user_id` to older local
  databases. A lock protects the shared connection used by the app factory.
- **JWT plus per-user data:** passwords use salted scrypt hashes; access tokens
  carry a user id; expense writes and all reads are scoped to that id.
- **Compatibility API key:** the previous API-key mode is retained for scripts,
  but it is intentionally a shared namespace rather than pretending to provide
  multi-user isolation.
- **React + Vite:** the development server gives fast feedback and a proxy
  avoids CORS setup during local development. The production build can be
  served directly by FastAPI.
- **App factory:** `create_app()` accepts database/auth/CORS settings so tests
  use isolated temporary databases without global state.

## Tests

The pytest suite covers:

- expense creation, normalization, rounding, defaults, and validation errors;
- category/date filtering and empty results;
- month-over-month calculations, January rollover, and the 20% insight boundary;
- API-key behavior;
- JWT registration, login, invalid credentials/tokens, duplicate users,
  missing configuration, and per-user isolation.

## Project Layout

```text
app/
  db.py       SQLite schema, migration, and query helpers
  models.py   Pydantic request/response models and money helpers
  auth.py     JWT/API-key auth and password hashing
  routes.py   auth, expenses, summary, and health routes
  main.py     FastAPI app factory and CORS/static setup
frontend/
  src/        React UI
  vite.config.js
  .env.example
tests/        pytest suite
run.py        uvicorn entrypoint
.env.example  backend environment template
```

## What I Would Do Differently With More Time

- Use short-lived access tokens with rotating refresh tokens, account recovery,
  email verification, and a dedicated password-hashing library such as Argon2.
- Add pagination, edit/delete endpoints, idempotency keys, and server-side
  request rate limiting.
- Replace the lightweight schema bootstrap with Alembic migrations and move to
  Postgres for multi-instance production deployments.
- Add timezone-aware date handling, budgets, richer trend charts, and CI that
  runs backend tests plus a frontend build.
- Containerize and deploy the built React/FastAPI app with a persistent SQLite
  volume or managed Postgres database.
