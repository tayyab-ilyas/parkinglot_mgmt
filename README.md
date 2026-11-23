# Parking Lot Automation

A local web app that replaces paper parking tickets. A FastAPI modular monolith, one Postgres database and a
React console with role-based screens: **Entry** and **Exit** for attendants, and **Overview, Lots, Pricing,
Users and Audit log** for admins. One deployment serves every city and lot; each lot is a row of data.

- **Entry:** record the plate and vehicle type, assign a compatible free spot, and print a ticket with a QR code
  and its tariff. When the lot is full, the screen lists other lots in the same city that have space.
- **Exit:** find a ticket by code (or by plate if lost), show an itemised bill, take a simulated payment and free the spot.
- **Admin:** live occupancy, revenue and traffic charts, a vehicle-type × spot-size breakdown, adding and disabling
  lots, laying out levels and spots, pricing rules, users and their lots, and an audit trail.
- **Guarantee:** two cars can never hold the same spot. The database enforces this, not application code.

---

## Contents

1. [Quick start (Docker)](#1-quick-start-docker)
2. [Demo accounts and data](#2-demo-accounts-and-data)
3. [Local development without Docker for the app](#3-local-development)
4. [Tests](#4-tests)
5. [Database migrations](#5-database-migrations)
6. [Command reference](#6-command-reference)
7. [Configuration](#7-configuration)
8. [Packages and libraries](#8-packages-and-libraries)
9. [Project layout](#9-project-layout)
10. [API reference](#10-api-reference)
11. [How fees are calculated](#11-how-fees-are-calculated)
12. [Where the guarantees live](#12-where-the-guarantees-live)
13. [Extension points and known shortcuts](#13-extension-points-and-known-shortcuts)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Quick start (Docker)

You need Docker Desktop (Compose v2) running.

```sh
docker compose up -d --build
```

| Service | URL | What it is |
|---------|-----|------------|
| `web` | http://localhost:8080 | React console served by nginx; proxies `/api` to the API |
| `api` | http://localhost:8000/api/health | FastAPI. Interactive docs at http://localhost:8000/docs |
| `db`  | `localhost:5432` | Postgres 16 (user, password and database are all `parking`) |

When the `api` container starts it runs, in order: `alembic upgrade head` (schema), `python -m app.seed`
(demo data, only if the database has no users) and `uvicorn`.

To see the dashboards with data, add 30 days of simulated history (see [section 2](#2-demo-accounts-and-data)):

```sh
docker compose exec api python -m app.seed --history 30
```

Stop with `docker compose down`. Add `-v` to also delete the database volume and start from empty.

## 2. Demo accounts and data

| Username | Password | Access |
|----------|----------|--------|
| `admin` | `admin123` | Every screen, every lot |
| `attendant` | `attendant123` | Entry and Exit at **MG Road** only |

The seed creates the city Bengaluru with two lots (MG Road and Koramangala). Each lot has levels B1 and G, each
level has 4 small, 8 medium and 2 large spots, and each lot has pricing for car, motorcycle and truck.

`python -m app.seed --history N` adds N past days of closed tickets with payments. Fees come from the real fee
calculator, with weekday and weekend traffic and morning and evening peaks. Simulated plates contain `SIM`, and
the command skips itself if they already exist.

**Change both passwords and `JWT_SECRET` before any use beyond a demo.**

## 3. Local development

Run Postgres in Docker, and the API and frontend on your machine for hot reload.

Requirements: Python 3.12+, Node 22+, Docker.

```sh
# 1. Database
docker compose up -d db

# 2. Backend (from ./backend)
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # macOS/Linux: .venv/bin/pip
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.seed --history 30
.venv/Scripts/uvicorn app.main:app --reload            # http://localhost:8000, docs at /docs

# 3. Frontend (from ./frontend, in a second terminal)
npm install
npm run dev                                            # http://localhost:5173, proxies /api to :8000
```

On macOS and Linux, replace `.venv/Scripts/` with `.venv/bin/`. In Windows PowerShell, use `.\.venv\Scripts\`.

## 4. Tests

The tests need the `db` container. They create and use a separate `parking_test` database, so your demo data is
never touched. Each test starts from a freshly seeded schema.

```sh
# from ./backend, on your machine
.venv/Scripts/python -m pytest -q

# or inside the running API container
docker compose exec api python -m pytest -q

# one file or one test
.venv/Scripts/python -m pytest -q tests/test_parking.py
.venv/Scripts/python -m pytest -q tests/test_parking.py::test_parallel_entries_never_share_a_spot
```

| File | Covers |
|------|--------|
| `tests/test_pricing.py` | Fee maths: grace period, hour rounding, 24 h cap, multi-day stays, lost ticket, breakdown lines |
| `tests/test_parking.py` | 50 parallel entries into 10 spots, same-plate race, upsizing, lot full, entry → quote → checkout, lost ticket, lot scoping, occupied spot, pricing supersede, revenue |
| `tests/test_reporting.py` | Rate card, fee breakdown on quotes, analytics, live vehicle × size mix, cross-lot overview, adding and disabling lots |
| `tests/test_integration.py` | Cross-module flows over HTTP: new lot from setup to paid exit, login/logout, deactivated user locked out, lot reassignment, input errors, no price set, closed level skipped, price change not touching parked cars |
| `tests/test_cache_unit.py` | The cache store alone, on a fake clock: hits, TTL expiry, errors not cached, prefix clears, overlapping write, eviction, write-to-area map, stats, parallel readers |
| `tests/test_cache.py` | The cache through the app: rollback vs commit, rate card after publish, live counts after entry and checkout, fresh fee on a cached ticket, `/api/cache` |

The frontend has no unit tests; `npm run build` type-checks it with `tsc`.

## 5. Database migrations

The schema is managed by Alembic (`backend/alembic/versions/`). After changing a model:

```sh
# from ./backend, with the db running
.venv/Scripts/alembic revision --autogenerate -m "describe the change"
# read the generated file in alembic/versions/ and fix anything autogenerate missed, then:
.venv/Scripts/alembic upgrade head
```

Other useful commands: `alembic current` (applied revision), `alembic history`, `alembic downgrade -1`.

## 6. Command reference

| Task | Command | Run from |
|------|---------|----------|
| Build and start everything | `docker compose up -d --build` | repo root |
| Rebuild only the API or web | `docker compose up -d --build api` / `web` | repo root |
| Follow logs | `docker compose logs -f api` | repo root |
| Stop / wipe data | `docker compose down` / `docker compose down -v` | repo root |
| Open a SQL shell | `docker compose exec db psql -U parking parking` | repo root |
| Seed demo data | `python -m app.seed` | backend |
| Seed + N days of history | `python -m app.seed --history 30` | backend |
| Apply migrations | `alembic upgrade head` | backend |
| New migration | `alembic revision --autogenerate -m "..."` | backend |
| Run the API with reload | `uvicorn app.main:app --reload` | backend |
| Run tests | `python -m pytest -q` | backend |
| Install frontend deps | `npm install` (or `npm ci` for the lockfile exactly) | frontend |
| Dev server | `npm run dev` | frontend |
| Type-check and production build | `npm run build` (output in `frontend/dist`) | frontend |

Inside containers, prefix backend commands with `docker compose exec api`, e.g.
`docker compose exec api alembic current`.

## 7. Configuration

| Variable | Default | Used by |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+psycopg://parking:parking@localhost:5432/parking` (`@db:5432` in Compose) | API, Alembic, seed, tests |
| `JWT_SECRET` | `dev-secret-change-me` | API: signs the login cookie. Set it in your shell or a `.env` file next to `docker-compose.yml` |

Other settings live in code:

- Login sessions last 12 hours (`TTL` in `backend/app/auth.py`).
- Which spot sizes each vehicle type may use, in order (`COMPATIBLE_SIZES` in `backend/app/enums.py`).
- Each lot's timezone (defaults to `Asia/Kolkata`) and currency (defaults to `INR`) are stored on the lot.

## 8. Packages and libraries

### Backend (Python 3.12, `backend/requirements.txt`)

| Package | Version | Why it is here |
|---------|---------|----------------|
| `fastapi` | 0.115.6 | HTTP API, request validation (with Pydantic), dependency injection for auth and DB sessions, OpenAPI docs at `/docs` |
| `uvicorn[standard]` | 0.34.0 | ASGI server that runs FastAPI |
| `sqlalchemy` | 2.0.36 | ORM models, queries, transactions; raw SQL for the spot claim and analytics |
| `psycopg[binary]` | 3.2.3 | Postgres driver used by SQLAlchemy |
| `alembic` | 1.14.0 | Schema migrations |
| `pyjwt` | 2.10.1 | Signs and checks the session token kept in an httpOnly cookie |
| `bcrypt` | 4.2.1 | Password hashing |
| `tzdata` | 2024.2 | Timezone database for `zoneinfo` (needed on Windows and slim images) |
| `pytest` | 8.3.4 | Test runner |
| `httpx` | 0.28.1 | Required by FastAPI's `TestClient` in the API tests |

Pydantic (v2) comes with FastAPI and defines every request and response schema.

### Frontend (Node 22, `frontend/package.json`)

| Package | Version | Why it is here |
|---------|---------|----------------|
| `react`, `react-dom` | 18.3.1 | UI |
| `@tanstack/react-query` | 5.62.0 | Server state: fetching, caching, polling (live occupancy every 5 s), refetch after writes |
| `qrcode.react` | 4.1.0 | QR code on the printed ticket |
| `vite` | 5.4.11 | Dev server with `/api` proxy, production build |
| `@vitejs/plugin-react` | 4.3.4 | JSX and fast refresh for Vite |
| `typescript` | 5.6.3 | Types; `npm run build` fails on type errors |
| `@types/react`, `@types/react-dom` | 18.3.12 / 18.3.1 | React type definitions |

Not added on purpose: no chart library (the charts are small SVG components in `src/charts.tsx`), no router
(the sidebar switches screens), no CSS framework (one stylesheet, `src/styles.css`), and no icon package
(line icons are inline SVG paths in `src/ui.tsx`).

### Fonts and images

| Item | Source |
|------|--------|
| Reddit Sans (UI text) and JetBrains Mono (plates, ticket codes) | Google Fonts, linked in `frontend/index.html`. Without internet the UI falls back to the system font |
| `postgres:16-alpine` | Database image |
| `python:3.12-slim` | API image |
| `node:22-alpine` → `nginx:1.27-alpine` | Web image: builds the app, then serves `dist/` and proxies `/api/` |

### Design notes

- **Palette:** teal on off-white, with a matching dark mode that follows the OS setting. Colours are CSS custom
  properties at the top of `src/styles.css`.
- **Charts:** one teal hue for single-series charts. Vehicle types always keep the same colours: car blue
  `#2a78d6`, motorcycle orange `#eb6834`, truck green `#1baf7a` (dark mode has its own steps). This set was
  checked for colour-blind separation in light and dark.
- **Status colours** (good, warning, critical) always come with an icon and a word.

## 9. Project layout

```
docker-compose.yml            db, api, web
backend/
  Dockerfile                  migrate → seed → uvicorn
  alembic/                    env.py and versions/ (0001_initial_schema.py)
  app/
    main.py                   FastAPI app; mounts every router under /api
    db.py                     engine, session, Base
    auth.py                   password hashing, JWT cookie, current_user / admin_only / lot access
    errors.py                 AppError and the {code, message, details} error shape
    enums.py                  roles, sizes, states, vehicle types, COMPATIBLE_SIZES
    models.py                 imports every model (for Alembic and tests)
    seed.py                   demo data and --history simulation
    modules/
      identity/               users, user_lots, login/logout/me, user admin
      locations/              cities, lots, levels, spots (CRUD, bulk spots, out of service)
      pricing/                pricing rules, fee calculation and breakdown, public rate card
      parking/                tickets: entry (spot claim), lookup, quote, checkout
      payments/               Payment model, PaymentGateway interface, DummyGateway
      reporting/              occupancy, analytics, live mix, overview, revenue, audit log
      audit/                  AuditLog model and record()
  tests/                      conftest.py, test_pricing.py, test_parking.py, test_reporting.py, test_integration.py, test_cache*.py
frontend/
  Dockerfile, nginx.conf
  index.html                  fonts, root element
  src/
    main.tsx                  React Query client; any 401 returns to login
    App.tsx                   login, sidebar shell, lot switcher, page routing
    api.ts                    fetch wrapper, types, money/time formatting
    ui.tsx                    icons, cards, meters, status pills, rate card, size chips
    charts.tsx                column chart, segmented bar, vehicle × size matrix, chart/table card
    styles.css                tokens (light and dark), components, responsive and print styles
    pages/                    Entry, Exit, Dashboard (Overview), Lots, Pricing, Users, Audit
```

## 10. API reference

Every route is under `/api`. Errors share one shape: `{ "code": "LOT_FULL", "message": "...", "details": {...} }`.
Money is always an integer in minor units (paise). Full interactive docs: http://localhost:8000/docs.

**Who can call it:** *any* = logged-in user; *lot* = admin, or an attendant assigned to that lot; *admin* = admins only.

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| POST | `/auth/login` | public | Log in; sets the `session` cookie |
| POST | `/auth/logout` | any | Clear the cookie |
| GET | `/me` | any | Current user and assigned lot ids |
| GET | `/lots?city_id=` | any | Lots the caller may see, with free-spot counts |
| POST | `/lots/{lotId}/tickets` | lot | Issue a ticket. 409 `VEHICLE_ALREADY_PARKED`, `LOT_FULL` (with alternatives), `LOT_INACTIVE`, `NO_PRICING_RULE` |
| GET | `/lots/{lotId}/tickets?plate=&status=OPEN` | lot | Search tickets (lost-ticket lookup, active list) |
| GET | `/tickets/{code}?lost=` | lot | Ticket, current fee, breakdown lines and the tariff locked at entry |
| POST | `/tickets/{code}/checkout` | lot | `{expected_amount, lost}`: pay, close, free the spot. 409 `FEE_CHANGED`, `TICKET_CLOSED` |
| GET | `/lots/{lotId}/rates` | lot | Public rate card and allowed spot sizes per vehicle type |
| GET | `/lots/{lotId}/occupancy` | lot | Level × size: total, free, occupied, out of service |
| GET | `/lots/{lotId}/parked` | lot | Vehicles parked now by vehicle type × spot size |
| GET | `/lots/{lotId}/analytics?from_date=&to_date=` | admin | Daily revenue, entries and exits; arrivals by hour; per-vehicle stats; vehicle × size matrix |
| GET | `/reports/overview` | admin | Per lot: capacity, occupied, entries and revenue today |
| GET | `/reports/revenue?lot_id=&from_date=&to_date=` | admin | Revenue per local day |
| GET, POST | `/cities` | admin | List or create cities |
| PATCH | `/cities/{id}` | admin | Rename or retire a city |
| POST | `/cities/{id}/lots` | admin | Add a lot `{name, timezone?, currency?}` |
| PATCH | `/lots/{id}` | admin | Rename, change timezone, or enable/disable `{active}` |
| GET, POST | `/lots/{id}/levels` | admin | List or add levels |
| PATCH | `/levels/{id}` | admin | Rename, reorder, close or reopen a level |
| GET | `/levels/{id}/spots` | admin | List spots |
| POST | `/levels/{id}/spots` | admin | Bulk add `{size, count, prefix, start}` |
| PATCH | `/spots/{id}` | admin | `{state: FREE \| OUT_OF_SERVICE}`; 409 `SPOT_OCCUPIED` |
| GET, POST | `/lots/{id}/pricing-rules` | admin | Rule history; a new rule replaces the current one for that vehicle type |
| POST | `/pricing-rules/{id}/retire` | admin | Retire a rule |
| GET, POST | `/users` | admin | List or create users |
| PATCH | `/users/{id}` | admin | Password, role, active |
| PUT | `/users/{id}/lots` | admin | Set an attendant's lots (`[lotId, ...]`) |
| GET | `/audit-logs?entity=&entity_id=&limit=` | admin | Latest changes |
| GET | `/cache` | admin | Cache contents (keys, seconds left) and hits/misses/clears per area |
| GET | `/health` | public | Liveness |

## 11. How fees are calculated

Each pricing rule has: free minutes, an hourly rate, an optional 24-hour cap and a lost-ticket fee.

1. A stay within the free minutes costs nothing.
2. Past that, every **started** hour is billed from arrival (61 minutes = 2 hours).
3. Any 24 hours costs at most the cap. Each full day costs the cap, and the remaining hours are capped too.
4. A lost ticket adds the lost-ticket fee.
5. The rule in force at **entry** applies to the whole stay. Rules are never edited, only replaced or retired.

The server returns the bill as lines (`fee_breakdown` in `backend/app/modules/pricing/service.py`), and the Exit
screen shows exactly those lines. Checkout sends the amount the attendant saw. If an hour ticked over in
between, the server answers `FEE_CHANGED` with the new amount instead of charging something else.

## 12. Where the guarantees live

- **One car per spot, one open ticket per plate:** partial unique indexes on `tickets`
  (`uq_open_ticket_spot`, `uq_open_ticket_plate` in `app/modules/parking/models.py`).
- **Spot claim:** a single `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1)`
  (`CLAIM_SPOT` in `app/modules/parking/service.py`). Parallel entries never wait on each other or pick the same spot.
- **One current rate per lot and vehicle type:** partial unique index `uq_current_rule`.
- **No double charge:** `payments.ticket_id` is unique.
- **Nothing half-done:** each state change and its audit row commit in one transaction.
- **Attendant scoping:** every lot route checks `ensure_lot_access`; ticket routes check the ticket's lot.

## 13. Extension points and known shortcuts

- **Real payments:** implement `PaymentGateway` in `app/modules/payments/gateway.py`. The dummy charge runs
  inside the DB transaction. A real provider needs a pending payment row, commit, charge, then finalise (see the
  `shortcut:` comment in `checkout`).
- **New vehicle types or size rules:** `VehicleType` and `COMPATIBLE_SIZES` in `app/enums.py`, plus a migration
  for the check constraint.
- **Cameras, barriers, reservations:** new callers of `issue_ticket` and `checkout`; `SpotState` can gain `RESERVED`.
- **Analytics at scale:** queries scan a lot's tickets in the chosen window. Add a daily rollup table when one
  lot passes about a million tickets a year (`shortcut:` comment in `reporting/router.py`).
- **Response cache:** `app/cache.py` is an in-process store that caches every GET endpoint. Keys start with an
  area (`live`, `tickets`, `reports`, `audit`, `places`, `rates`, `pricing`, `users`) that sets its TTL. Every
  write already calls `audit.record()`, which marks the areas it affects; they are cleared right after the commit
  (a rollback clears nothing). Analytics and revenue are not cleared by ticket writes and can trail by up to 60 s.
  Ticket lookups cache the stored ticket, but the fee is always computed fresh, and the spot claim, checkout and
  login never touch the cache. Writes made outside the API (`--history`, psql) show up when the TTL runs out.
  It lives in one API process; with several workers or servers, move it to Redis.
- **Not built yet:** login rate limiting, refunds, an in-app theme switch, frontend unit tests.

List every deferred shortcut with: `grep -rn "shortcut:" backend frontend/src`.

## 14. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop is not running; start it |
| `port is already allocated` (5432, 8000, 8080) | Stop the other service, or change the left side of `ports` in `docker-compose.yml` |
| Dashboards are empty | Run `docker compose exec api python -m app.seed --history 30` |
| Logged out after a rebuild | Expected if `JWT_SECRET` changed; log in again |
| `ModuleNotFoundError: app` when running Alembic | Run it from `./backend` |
| Tests fail to connect | Start the database: `docker compose up -d db` |
| UI changes not visible at :8080 | Rebuild the web image: `docker compose up -d --build web` |
