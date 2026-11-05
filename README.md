# Roster SaaS

[![CI](https://github.com/Kayu2222/roster-saas/actions/workflows/ci.yml/badge.svg)](https://github.com/Kayu2222/roster-saas/actions/workflows/ci.yml)

Multi-tenant operations SaaS for small businesses (API + web app). Any company can sign up, switch on the features it needs, and run them fully isolated from every other company on the platform.

## Live demo

**https://ca-roster-api.graysea-b70f2022.australiaeast.azurecontainerapps.io**

Sign in to a demo hospital with `demo@example.com` / `riverside-demo` (manager role), or register your own company to see an empty, fully isolated tenant. API docs are at [`/docs`](https://ca-roster-api.graysea-b70f2022.australiaeast.azurecontainerapps.io/docs).

The app scales to zero when idle, so the first request after a quiet spell can take around 20 seconds. The demo account is shared, so data may have been changed by other visitors. All people in it are fictional.

| Week board: shifts as colour-coded magnets per job role | Bookings: find what's free, book it for a client |
|---|---|
| ![Week board](docs/screenshots/week-board.png) | ![Bookings](docs/screenshots/bookings.png) |
| **Client history: every booking and item used, in one place** | **Stock: reorder meters, low-stock warnings, ledger** |
| ![Client history](docs/screenshots/client-history.png) | ![Stock](docs/screenshots/stock.png) |

It models the three things a small business manages, the "3P":

| | What it is | Used by | Clinic example | Feature |
|---|---|---|---|---|
| **People** | staff with schedules and qualifications, and the clients they serve | time | nurses on shift, patients | Roster, Clients |
| **Property** | reusable assets | time (bookings that must not overlap) | beds, consult rooms | Resource bookings |
| **Products** | consumables | quantity (stock that must not go negative) | medicine, gloves | Stock |

**Stack:** Python · FastAPI · SQLAlchemy 2 · PostgreSQL · Alembic · JWT · pytest · React · TypeScript · Vite · Docker · GitHub Actions
**Cloud:** Azure Container Apps · Azure Database for PostgreSQL · Container Registry · Key Vault · Bicep · GitHub OIDC

## Why it's interesting

| Problem | How it's solved |
|---|---|
| Company A must never see Company B's data | Tenant isolation is enforced centrally in `app/core/tenancy.py`: every query on a tenant-scoped table is filtered automatically, and saving a row under another tenant raises an error. No endpoint writes `WHERE tenant_id = ...` by hand, so it can't be forgotten. |
| Forgetting to set a tenant shouldn't leak data | Querying tenant data with no tenant context **fails loudly** instead of returning all rows. The only opt-out is explicit (`bypass_tenant=True`), used only by login/sign-up. |
| Companies need different features | Each company switches modules on or off; endpoints are gated with `require_module(...)`. |
| Who can do what | Roles: `owner` (one per company, controls modules), `manager`, `staff`. |
| Credentials | Passwords hashed with bcrypt, never returned by the API. Login gives the same error for unknown email and wrong password. |
| Rosters that make sense | Each company defines its own job roles and shift templates. Shifts are rejected if they double-book a person, need a role the person doesn't hold, end before they start, or run longer than 16 hours. Overnight shifts are handled. |
| Two people booking the last free room at the same instant | Bookings check for overlaps **and** bump the resource's version (optimistic locking). If two requests pass the overlap check at the same moment, the second commit fails with 409 instead of creating a double booking. Tested with two real concurrent sessions. |
| Bugs or races that slip past the application | PostgreSQL **exclusion constraints** refuse overlapping shifts and active bookings at the database level, and **check constraints** refuse anything ending before it starts. The app turns these into clean 409s. |
| Two people taking the last box of stock at once | Stock changes are one atomic `UPDATE ... SET on_hand = on_hand - n WHERE on_hand >= n`, so the second request matches no row and gets a clear 409. A `CHECK (on_hand >= 0)` constraint backs it up. Every change also writes a row to an append-only **stock ledger**, so the current number can always be explained. |
| A stocktake while stock is moving | Counts are compare-and-set: "set it to what I counted, only if it's still the number I saw". Otherwise 409, count again. |
| Editing a resource someone else just changed | Edits must send the `version` they read; stale edits get 409 instead of silently overwriting. |

## Web app

A React + TypeScript single-page app in [`frontend/`](frontend), served by FastAPI from the same origin as the API (one URL, no CORS).

- **Week board:** shifts appear as colour-coded "magnets" per job role; managers add shifts from dropdowns of their own people and shift types, and people who don't hold the required role are shown but can't be picked.
- **Today:** who is on shift now and what is booked.
- **Bookings:** pick a time, see only what is free, book it. Staff see only their own bookings.
- **Clients:** the people you serve, with one history of every bed or room booked and every item used for them.
- **Stock:** on-hand levels with a reorder meter, receive, use (optionally for a client), stocktake, and a per-product ledger.
- **People, resources, company features** for owners and managers; staff get a read-only, personal view.

## Run with Docker (API + PostgreSQL)

```bash
docker compose up --build
```

Open http://localhost:8000/docs. The container applies the database migrations on start. `docker compose down -v` stops everything and deletes the data.

## Run locally without Docker (SQLite)

API:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs, call `POST /api/auth/register`, then click **Authorize** and paste the `access_token`.

Web app with live reload (needs Node 22), in a second terminal:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173, forwards /api to :8000
```

```bash
pytest -q                     # fast, in-memory SQLite
```

To run the same suite against PostgreSQL with the real migrated schema (CI does both):

```bash
docker compose up -d db
# PowerShell: $env:TEST_DATABASE_URL="postgresql+psycopg://roster:roster@localhost:5433/roster"
export TEST_DATABASE_URL=postgresql+psycopg://roster:roster@localhost:5433/roster
pytest -q                     # wipes that database first
```

## Deployment on Azure

```
git push ──> GitHub Actions: tests (SQLite + PostgreSQL) ──> Docker smoke test ──> deploy job
                                                                                     │ OIDC sign-in, no stored password
                                                                                     ▼
                         Azure Container Registry ◀── push image ────────────────────┘
                                  │ pull (managed identity)
                                  ▼
 users ──HTTPS──> Azure Container Apps (scales to zero) ──> Azure Database for PostgreSQL
                                  │ encrypted app secrets, copied at deploy time
                                  ▼
                               Key Vault (system of record: database URL, JWT secret)
```

Everything is defined in [`infra/main.bicep`](infra/main.bicep) (Infrastructure as Code).

| Concern | Choice |
|---|---|
| No passwords in GitHub | GitHub Actions signs in with **OIDC** through a federated managed identity, trusted only for pushes to `main` of this repository. The repo stores identifiers only. |
| No passwords in config | Database URL and JWT secret are generated by `setup.ps1` (never printed or saved), kept in **Key Vault**, and handed to the app as **encrypted Container Apps secrets** at deploy time. Australia East runs Container Apps *express* environments, which can't reference Key Vault directly, hence the copy. |
| Least privilege | The deploy identity can push images and update resources in this one resource group only. The app identity can only pull images. |
| Cost | Sized to the Azure for Students free allowances: Container Apps consumption plan with scale-to-zero, PostgreSQL Burstable B1ms with 32 GB, Standard registry. Logs capped at 0.1 GB/day. |
| Trade-offs (documented, deliberate) | The database accepts connections from Azure services (password + TLS still required) instead of a private VNet, and the app runs one replica so start-up migrations are simple. Both are the next things to change for real production traffic. |

**Set up once** (needs Azure CLI and Docker Desktop, signed in with `az login`):

```powershell
.\infra\setup.ps1
```

It creates the resource group in `australiaeast`, deploys the infrastructure, pushes the first image and prints the GitHub repository variables to add. After that, every push to `main` is tested and deployed automatically.

**Remove everything:** `.\infra\teardown.ps1`

### Demo data

[`scripts/seed_demo.py`](scripts/seed_demo.py) builds the demo hospital through the public API only (standard library, no installs), so it also works as an end-to-end check of a deployment: 7 people with job roles, two weeks of rota, beds, consult rooms and a van, clients with bookings, and stock with a ledger.

```bash
python scripts/seed_demo.py                                   # seed the live deployment
python scripts/seed_demo.py --url http://localhost:8000       # or a local one
python scripts/seed_demo.py --refresh                         # top up this week's and next week's rota and bookings
```

The owner password is random unless `DEMO_OWNER_PASSWORD` is set, and is printed once. `--refresh` signs in as the demo manager and skips anything that already exists (the API answers 409).

## API

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/register` | anyone: creates company + owner, picks modules |
| POST | `/api/auth/login` | anyone |
| GET | `/api/me` | any signed-in user |
| GET | `/api/tenant` | any signed-in user |
| PUT | `/api/tenant/modules` | owner |
| GET | `/api/users`, `/api/users/{id}` | any signed-in user (own company only) |
| POST | `/api/users` | owner, manager (only owner can add managers) |
| GET / POST / DELETE | `/api/roster/job-roles` | read: anyone · write: owner, manager |
| GET / PUT | `/api/roster/staff/{user_id}/job-roles` | read: anyone · write: owner, manager |
| GET / POST / DELETE | `/api/roster/shift-types` | read: anyone · write: owner, manager |
| POST / DELETE | `/api/roster/shifts` | owner, manager |
| GET | `/api/roster/shifts?from=&to=&user_id=` | managers see all; staff only their own |
| GET | `/api/roster/shifts/mine?from=&to=` | any signed-in user |
| GET / POST / DELETE | `/api/resources/types` | read: anyone · write: owner, manager |
| GET / POST | `/api/resources` | read: anyone · create: owner, manager |
| GET / PATCH | `/api/resources/{id}` | read: anyone · edit (needs `version`): owner, manager |
| GET | `/api/resources/availability?start_at=&end_at=&type_id=` | anyone: which resources are free |
| POST | `/api/resources/bookings` | anyone in the company |
| GET | `/api/resources/bookings?from=&to=&resource_id=` | managers see all; staff only their own |
| POST | `/api/resources/bookings/{id}/cancel` | own bookings; managers any |
| GET / POST | `/api/clients?q=` | anyone in the company (search by name, email, phone) |
| GET / PATCH | `/api/clients/{id}` | anyone; archiving: owner, manager |
| GET | `/api/clients/{id}/activity` | bookings and stock used for this client |
| GET / POST / PATCH | `/api/inventory/products` | read: anyone · write: owner, manager |
| POST | `/api/inventory/products/{id}/use` | anyone (optionally `client_id`) |
| POST | `/api/inventory/products/{id}/receive`, `/count` | owner, manager |
| GET | `/api/inventory/movements` | the stock ledger; staff see only their own entries |
| GET | `/health` | anyone |

## Project layout

```
app/
  core/config.py     settings from env / .env
  core/security.py   bcrypt + JWT
  core/tenancy.py    automatic tenant isolation (the key file)
  core/errors.py     one business-rule error type, one handler
  models.py          Tenant, User
  schemas.py         request/response models
  deps.py            current user, role and module checks
  routers/           auth, company, users
  modules/roster/    models, schemas, service (business rules), router
  modules/resources/ models, schemas, service (business rules), router
  modules/inventory/ products, stock ledger, atomic stock changes
  routers/clients.py the people you serve, and their combined history
tests/               isolation, auth, roles, module gating, roster and booking rules, concurrency,
                     PostgreSQL constraints
migrations/          Alembic: 0001 schema, 0002 exclusion + check constraints, 0003 clients and stock
frontend/            React + TypeScript web app (Vite)
app/frontend.py      serves the built web app without shadowing API routes
Dockerfile           3-stage image (Node build, Python deps, slim runtime), non-root, migrates on start
docker-compose.yml   local API + PostgreSQL
.github/workflows/   CI/CD: tests on SQLite and PostgreSQL, migration drift check, Docker smoke test,
                     deploy to Azure
infra/               Bicep infrastructure, one-time setup and teardown scripts
scripts/seed_demo.py demo hospital through the public API (also an end-to-end check)
docs/screenshots/    images used in this README
```

## Roadmap

- [x] **Step 1** – Multi-tenant core: sign-up, login, roles, module switching, isolation tests
- [x] **Step 2** – Roster module: company-defined roles and shift types, date-based shifts, clash checks
- [x] **Step 3** – Resource module: company-defined resource types, bookings with overlap checks, optimistic locking
- [x] **Step 4a** – Docker, docker-compose, PostgreSQL, Alembic migrations, database constraints, GitHub Actions CI
- [x] **Step 4b** – Deploy to Azure Container Apps (Bicep), GitHub Actions deploys with OIDC
- [x] **Step 5a** – Web app: sign-up with feature choice, week board, bookings, people, resources
- [x] **Step 6** – 3P: clients (people served), stock module with ledger and race-safe quantities, bookings for a client
- [x] **Step 7** – Live demo: seed script, demo login, screenshots
- **Not planned:** drag and drop on the board (originally Step 5b). Dropdowns already cover every action, and the effort is better spent on the backend.

## Design decisions

- **Shared database, `tenant_id` column** (vs. one database per tenant): cheapest to run and simplest to operate at this scale; isolation is enforced in one place and covered by tests.
- **One email = one company** for the MVP. Users belonging to several companies would need a membership table; deliberately left out.
- **Business rules live in each module's `service.py`, not in the routes**, so they read as plain logic and are tested end to end.
- **Cancelled bookings are kept**, not deleted, so there is a history of who booked what.
- **Clients hold no sensitive data by design** (contact details and a short practical note only). It keeps the product general-purpose and avoids storing health information.
- **Time vs quantity:** assets (booked by time) are protected by exclusion constraints and optimistic locking; products (used by quantity) by guarded atomic updates and a ledger. Same problem, different shape, matching tool.
- **Shift times are company-local wall-clock times** (no timezone). A per-company timezone can be added without changing the tables.
- **Two layers against double-booking:** the application checks first (clear error messages, works on any database); PostgreSQL exclusion constraints are the backstop that cannot be bypassed by concurrent requests or future bugs. Resource bookings additionally use optimistic locking.
- **Schema changes go through Alembic migrations**; CI fails if the models and migrations drift apart (`alembic check`). Local SQLite still creates tables on startup for convenience.
