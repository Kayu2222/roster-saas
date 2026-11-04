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

## API (step 1)

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/register` | anyone: creates company + owner, picks modules |
| POST | `/api/auth/login` | anyone |
| GET | `/api/me` | any signed-in user |
| GET | `/api/tenant` | any signed-in user |
| PUT | `/api/tenant/modules` | owner |
| GET | `/api/users`, `/api/users/{id}` | any signed-in user (own company only) |
| POST | `/api/users` | owner, manager (only owner can add managers) |
| GET | `/api/roster/status`, `/api/resources/status` | companies with that module on |
| GET | `/health` | anyone |

## Project layout

```
app/
  core/config.py     settings from env / .env
  core/security.py   bcrypt + JWT
  core/tenancy.py    automatic tenant isolation (the key file)
  models.py          Tenant, User
  schemas.py         request/response models
  deps.py            current user, role and module checks
  routers/           auth, company, users, module entry points
tests/               isolation, auth, roles and module gating
```

## Roadmap

- [x] **Step 1** – Multi-tenant core: sign-up, login, roles, module switching, isolation tests
- [ ] **Step 2** – Roster module: company-defined roles and shift types, date-based shifts, clash checks
- [ ] **Step 3** – Resource module: company-defined resource types, bookings with overlap checks, optimistic locking
- [ ] **Step 4** – Docker, GitHub Actions (OIDC), Azure Container Apps, PostgreSQL, Alembic, Key Vault
- [ ] **Step 5** – Web front end

## Design decisions

- **Shared database, `tenant_id` column** (vs. one database per tenant): cheapest to run and simplest to operate at this scale; isolation is enforced in one place and covered by tests.
- **One email = one company** for the MVP. Users belonging to several companies would need a membership table; deliberately left out.
- Tables are created on startup for now; migrations (Alembic) come with PostgreSQL in step 4.
