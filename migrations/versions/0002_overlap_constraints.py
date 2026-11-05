"""Database-level safety nets (PostgreSQL only).

The application already rejects overlapping shifts and bookings, but two requests
arriving at the same instant can both pass an application check. These constraints
make the database itself refuse the second row, whatever the application does.

- Exclusion constraints: no two shifts for the same person, and no two ACTIVE
  bookings for the same resource, may overlap in time. '[)' means the end time is
  exclusive, so back-to-back slots (09:00-13:00, 13:00-17:00) are allowed.
- Check constraints: nothing may end before it starts.

SQLite (local dev and the fast test run) has no exclusion constraints, so this
migration does nothing there; the application-level checks still apply.

Revision ID: 0002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    # Lets a GiST index compare plain equality columns (tenant_id, user_id) next to time ranges.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute(
        """
        ALTER TABLE shifts ADD CONSTRAINT ex_shifts_no_overlap
        EXCLUDE USING gist (
            tenant_id WITH =,
            user_id WITH =,
            tsrange(start_at, end_at, '[)') WITH &&
        )
        """
    )
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT ex_bookings_no_overlap
        EXCLUDE USING gist (
            tenant_id WITH =,
            resource_id WITH =,
            tsrange(start_at, end_at, '[)') WITH &&
        ) WHERE (status = 'ACTIVE')
        """
    )
    op.create_check_constraint("ck_shifts_end_after_start", "shifts", "end_at > start_at")
    op.create_check_constraint("ck_bookings_end_after_start", "bookings", "end_at > start_at")


def downgrade() -> None:
    if not _is_postgres():
        return
    op.drop_constraint("ck_bookings_end_after_start", "bookings", type_="check")
    op.drop_constraint("ck_shifts_end_after_start", "shifts", type_="check")
    op.execute("ALTER TABLE bookings DROP CONSTRAINT ex_bookings_no_overlap")
    op.execute("ALTER TABLE shifts DROP CONSTRAINT ex_shifts_no_overlap")
