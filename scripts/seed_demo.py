#!/usr/bin/env python3
"""Create a demo hospital on a running Roster SaaS, through the public API only.

Standard library only, so it runs anywhere Python 3.10+ is installed:

    python scripts/seed_demo.py                      # seed the live Azure deployment
    python scripts/seed_demo.py --url http://localhost:8000
    python scripts/seed_demo.py --refresh            # add shifts and bookings for this week and next

The first run creates the company, people, rosters, resources, clients, bookings and stock.
Later runs with --refresh sign in as the demo manager and top up the rota for the current
weeks, so the demo never looks empty. Everything goes through the same endpoints the web app
uses, so the script doubles as an end-to-end check of a deployment.

All people, clients and contact details are fictional.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

LIVE_URL = "https://ca-roster-api.graysea-b70f2022.australiaeast.azurecontainerapps.io"

COMPANY = "Riverside Community Hospital (demo)"
OWNER = ("Olivia Bennett", "riverside.owner@example.com")
# The public demo login (shown in the README). A manager can see and do everything
# except change the company's modules, which stays with the owner.
MANAGER = ("Marcus Reid", "demo@example.com")
DEFAULT_DEMO_PASSWORD = "riverside-demo"

JOB_ROLES = ["Registered Nurse", "Doctor", "Receptionist"]

# name, email, job roles
STAFF = [
    ("Amelia Chen", "riverside.amelia@example.com", ["Registered Nurse"]),
    ("Liam O'Brien", "riverside.liam@example.com", ["Registered Nurse"]),
    ("Priya Nair", "riverside.priya@example.com", ["Registered Nurse"]),
    ("Dr Sophie Martin", "riverside.sophie@example.com", ["Doctor"]),
    ("Dr James Walker", "riverside.james@example.com", ["Doctor"]),
    ("Grace Kim", "riverside.grace@example.com", ["Receptionist", "Registered Nurse"]),
]

# name, start, end, job role
SHIFT_TYPES = [
    ("Morning", "07:00", "15:00", "Registered Nurse"),
    ("Evening", "15:00", "23:00", "Registered Nurse"),
    ("Night", "23:00", "07:00", "Registered Nurse"),
    ("Clinic", "08:30", "17:00", "Doctor"),
    ("Front desk", "08:00", "16:30", "Receptionist"),
]

# type, name, location
RESOURCES = [
    ("Bed", "Bed 1", "Ward A"),
    ("Bed", "Bed 2", "Ward A"),
    ("Bed", "Bed 3", "Ward A"),
    ("Bed", "Bed 4", "Ward B"),
    ("Consult room", "Consult room 1", "Ground floor"),
    ("Consult room", "Consult room 2", "Ground floor"),
    ("Vehicle", "Patient transport van", "Car park"),
]

# Practical notes only: the product deliberately stores no health information.
CLIENTS = [
    ("Margaret Hughes", "margaret.hughes@example.com", "0400 000 101", "Prefers morning appointments"),
    ("Tom Nguyen", "tom.nguyen@example.com", "0400 000 102", "Interpreter: Vietnamese"),
    ("Aisha Rahman", "aisha.rahman@example.com", "0400 000 103", "Contact by SMS, not phone calls"),
    ("Daniel Costa", None, "0400 000 104", "Needs wheelchair access"),
    ("Ruth Fischer", "ruth.fischer@example.com", "0400 000 105", "Daughter usually drives her in"),
    ("Ben Taylor", "ben.taylor@example.com", "0400 000 106", None),
]

# name, unit, reorder level, opening stock
PRODUCTS = [
    ("Disposable gloves (M)", "box", 10, 24),
    ("Surgical masks", "box", 10, 30),
    ("Paracetamol 500 mg", "pack", 20, 60),
    ("Saline 0.9% 500 ml", "bag", 15, 22),
    ("Wound dressings", "pack", 10, 14),
    ("Hand sanitiser 500 ml", "bottle", 6, 12),
]


class Api:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.token: str | None = None

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, raw.decode(errors="replace")

    def must(self, method: str, path: str, body: dict | None = None):
        status, payload = self.call(method, path, body)
        if status >= 300:
            sys.exit(f"{method} {path} failed with {status}: {payload}")
        return payload

    def maybe(self, method: str, path: str, body: dict | None = None):
        """Like must(), but a 409 (clash or already exists) is skipped instead of fatal."""
        status, payload = self.call(method, path, body)
        if status == 409:
            return None
        if status >= 300:
            sys.exit(f"{method} {path} failed with {status}: {payload}")
        return payload

    def wait_until_up(self) -> None:
        # The Azure app scales to zero, so the first request can take a while.
        for _ in range(30):
            try:
                if self.call("GET", "/health")[0] == 200:
                    return
            except (urllib.error.URLError, TimeoutError):
                pass
            print("  waiting for the API to wake up...")
            time.sleep(5)
        sys.exit(f"{self.base} did not answer /health")


def at(day: date, hhmm: str) -> str:
    """Company-local wall-clock time, no timezone, as the API expects."""
    return f"{day.isoformat()}T{hhmm}:00"


def week_days(weeks: int) -> list[date]:
    monday = date.today() - timedelta(days=date.today().weekday())
    return [monday + timedelta(days=i) for i in range(7 * weeks)]


def roster(api: Api, days: list[date], people: dict[str, str], shift_types: dict[str, str]) -> int:
    """Nurses rotate through morning, evening and night; doctors and reception work weekdays."""
    nurses = ["Amelia Chen", "Liam O'Brien", "Priya Nair"]
    plan: list[tuple[str, str, date]] = []
    for i, day in enumerate(days):
        plan += [
            (nurses[i % 3], "Morning", day),
            (nurses[(i + 1) % 3], "Evening", day),
            (nurses[(i + 2) % 3], "Night", day),
        ]
        if day.weekday() < 5:
            plan.append(("Dr Sophie Martin" if day.weekday() in (0, 2, 4) else "Dr James Walker", "Clinic", day))
            plan.append(("Grace Kim", "Front desk", day))
        else:
            plan.append(("Grace Kim", "Morning", day))  # Grace is also a nurse and helps out at weekends
    created = 0
    for person, shift_type, day in plan:
        body = {"user_id": people[person], "shift_type_id": shift_types[shift_type], "date": day.isoformat()}
        if api.maybe("POST", "/api/roster/shifts", body):
            created += 1
    return created


def book(api: Api, days: list[date], resources: dict[str, str], clients: dict[str, str]) -> int:
    """Consult appointments on weekdays, a few bed stays, and a transport run."""
    names = list(clients)
    slots = [("09:00", "09:30"), ("10:00", "10:45"), ("11:30", "12:00"), ("14:00", "14:30")]
    plan: list[dict] = []
    weekdays = [d for d in days if d.weekday() < 5]
    for i, day in enumerate(weekdays):
        for j, (start, end) in enumerate(slots[: 2 + i % 3]):
            plan.append({
                "resource_id": resources["Consult room 1" if j % 2 == 0 else "Consult room 2"],
                "start_at": at(day, start),
                "end_at": at(day, end),
                "purpose": "Consultation",
                "client_id": clients[names[(i + j) % len(names)]],
            })
    for week_start in days[::7]:
        plan += [
            {"resource_id": resources["Bed 1"], "start_at": at(week_start, "10:00"),
             "end_at": at(week_start + timedelta(days=2), "11:00"), "purpose": "Overnight observation",
             "client_id": clients["Margaret Hughes"]},
            {"resource_id": resources["Bed 3"], "start_at": at(week_start + timedelta(days=3), "08:00"),
             "end_at": at(week_start + timedelta(days=4), "12:00"), "purpose": "Day procedure and recovery",
             "client_id": clients["Daniel Costa"]},
            {"resource_id": resources["Patient transport van"], "start_at": at(week_start + timedelta(days=1), "13:00"),
             "end_at": at(week_start + timedelta(days=1), "14:30"), "purpose": "Pick-up from home",
             "client_id": clients["Ruth Fischer"]},
        ]
    return sum(1 for body in plan if api.maybe("POST", "/api/resources/bookings", body))


def seed(api: Api, weeks: int, demo_password: str, owner_password: str) -> None:
    print(f"Creating {COMPANY}")
    status, payload = api.call("POST", "/api/auth/register", {
        "company_name": COMPANY, "owner_name": OWNER[0], "email": OWNER[1],
        "password": owner_password, "modules": ["roster", "resource", "inventory"],
    })
    if status == 409:
        sys.exit("The demo company already exists. Use --refresh to top up shifts and bookings.")
    if status >= 300:
        sys.exit(f"Sign-up failed with {status}: {payload}")
    api.token = payload["access_token"]

    print("People and job roles")
    roles = {name: api.must("POST", "/api/roster/job-roles", {"name": name})["id"] for name in JOB_ROLES}
    people: dict[str, str] = {}
    manager = api.must("POST", "/api/users", {
        "name": MANAGER[0], "email": MANAGER[1], "password": demo_password, "role": "manager"})
    people[MANAGER[0]] = manager["id"]
    for name, email, job_roles in STAFF:
        user = api.must("POST", "/api/users", {
            "name": name, "email": email, "password": secrets.token_urlsafe(16), "role": "staff"})
        people[name] = user["id"]
        api.must("PUT", f"/api/roster/staff/{user['id']}/job-roles",
                 {"job_role_ids": [roles[r] for r in job_roles]})

    shift_types = {
        name: api.must("POST", "/api/roster/shift-types",
                       {"name": name, "start_time": start, "end_time": end, "job_role_id": roles[role]})["id"]
        for name, start, end, role in SHIFT_TYPES
    }

    print("Resources and clients")
    types = {t: api.must("POST", "/api/resources/types", {"name": t})["id"] for t in dict.fromkeys(r[0] for r in RESOURCES)}
    resources = {
        name: api.must("POST", "/api/resources", {"resource_type_id": types[t], "name": name, "location": loc})["id"]
        for t, name, loc in RESOURCES
    }
    clients = {
        name: api.must("POST", "/api/clients", {"name": name, "email": email, "phone": phone, "notes": notes})["id"]
        for name, email, phone, notes in CLIENTS
    }

    days = week_days(weeks)
    print(f"Shifts: {roster(api, days, people, shift_types)}")
    print(f"Bookings: {book(api, days, resources, clients)}")

    print("Stock and ledger")
    products = {
        name: api.must("POST", "/api/inventory/products",
                       {"name": name, "unit": unit, "reorder_level": level, "opening_stock": stock})
        for name, unit, level, stock in PRODUCTS
    }
    gloves, masks = products["Disposable gloves (M)"]["id"], products["Surgical masks"]["id"]
    api.must("POST", f"/api/inventory/products/{gloves}/receive", {"quantity": 20, "note": "Weekly delivery"})
    api.must("POST", f"/api/inventory/products/{masks}/receive", {"quantity": 10, "note": "Weekly delivery"})
    uses = [
        ("Disposable gloves (M)", 3, "Margaret Hughes"), ("Wound dressings", 5, "Daniel Costa"),
        ("Saline 0.9% 500 ml", 4, "Margaret Hughes"), ("Paracetamol 500 mg", 2, "Tom Nguyen"),
        ("Wound dressings", 2, "Ben Taylor"), ("Surgical masks", 2, None), ("Hand sanitiser 500 ml", 4, None),
    ]
    for product, qty, client in uses:
        body = {"quantity": qty, "note": "Ward round" if client is None else None}
        if client:
            body["client_id"] = clients[client]
        products[product] = api.must("POST", f"/api/inventory/products/{products[product]['id']}/use", body)
    paracetamol = products["Paracetamol 500 mg"]
    api.must("POST", f"/api/inventory/products/{paracetamol['id']}/count",
             {"counted": paracetamol["on_hand"] - 1, "expected": paracetamol["on_hand"], "note": "Monthly stocktake"})

    print("\nDone. Demo login (safe to publish):")
    print(f"  {MANAGER[1]} / {demo_password}")
    print("Owner login (keep private; only the owner can change modules):")
    print(f"  {OWNER[1]} / {owner_password}")


def refresh(api: Api, weeks: int, demo_password: str) -> None:
    api.token = api.must("POST", "/api/auth/login", {"email": MANAGER[1], "password": demo_password})["access_token"]
    people = {u["name"]: u["id"] for u in api.must("GET", "/api/users")}
    shift_types = {s["name"]: s["id"] for s in api.must("GET", "/api/roster/shift-types")}
    resources = {r["name"]: r["id"] for r in api.must("GET", "/api/resources")}
    clients = {c["name"]: c["id"] for c in api.must("GET", "/api/clients")}
    days = week_days(weeks)
    print(f"New shifts: {roster(api, days, people, shift_types)} (existing ones skipped)")
    print(f"New bookings: {book(api, days, resources, clients)} (existing ones skipped)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("ROSTER_URL", LIVE_URL), help="API base URL")
    parser.add_argument("--weeks", type=int, default=2, help="weeks of rota and bookings from this Monday (default 2)")
    parser.add_argument("--refresh", action="store_true", help="only top up shifts and bookings for the current weeks")
    args = parser.parse_args()

    demo_password = os.environ.get("DEMO_PASSWORD", DEFAULT_DEMO_PASSWORD)
    owner_password = os.environ.get("DEMO_OWNER_PASSWORD") or secrets.token_urlsafe(12)

    api = Api(args.url)
    print(f"API: {api.base}")
    api.wait_until_up()
    if args.refresh:
        refresh(api, args.weeks, demo_password)
    else:
        seed(api, args.weeks, demo_password, owner_password)


if __name__ == "__main__":
    main()
