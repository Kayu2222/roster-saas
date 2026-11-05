"""Brute-force protection: failed sign-ins per email and temporary lockouts.

Revision ID: 0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('login_throttle',
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('failures', sa.Integer(), nullable=False),
    sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('email')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('login_throttle')
