# Roster SaaS

Multi-tenant roster & resource management API. Any company can sign up, choose the modules it needs (staff rostering, resource booking, or both), and manage its own people — fully isolated from every other company on the platform.

**Stack:** Python · FastAPI · SQLAlchemy 2 · PostgreSQL (SQLite locally) · JWT · pytest
**Planned deployment:** Docker · GitHub Actions · Azure Container Apps

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
| Editing a resource someone else just changed | Edits must send the `version` they read; stale edits get 409 instead of silently overwriting. |

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs, call `POST /api/auth/register`, then click **Authorize** and paste the `access_token`.

```bash
pytest -q
```

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
tests/               isolation, auth, roles, module gating, roster and booking rules, concurrency
```

## Roadmap

- [x] **Step 1** – Multi-tenant core: sign-up, login, roles, module switching, isolation tests
- [x] **Step 2** – Roster module: company-defined roles and shift types, date-based shifts, clash checks
- [x] **Step 3** – Resource module: company-defined resource types, bookings with overlap checks, optimistic locking
- [ ] **Step 4** – Docker, GitHub Actions (OIDC), Azure Container Apps, PostgreSQL, Alembic, Key Vault
- [ ] **Step 5** – Web front end

## Design decisions

- **Shared database, `tenant_id` column** (vs. one database per tenant): cheapest to run and simplest to operate at this scale; isolation is enforced in one place and covered by tests.
- **One email = one company** for the MVP. Users belonging to several companies would need a membership table; deliberately left out.
- **Business rules live in each module's `service.py`, not in the routes**, so they read as plain logic and are tested end to end.
- **Cancelled bookings are kept**, not deleted, so there is a history of who booked what.
- **Shift times are company-local wall-clock times** (no timezone). A per-company timezone can be added without changing the tables.
- **Known limitation (roster):** the shift double-booking check runs in application code, so two simultaneous requests for the same person could both pass it. Resource bookings already close this gap with optimistic locking; for shifts, PostgreSQL (step 4) adds a database-level exclusion constraint.
- Tables are created on startup for now; migrations (Alembic) come with PostgreSQL in step 4.
