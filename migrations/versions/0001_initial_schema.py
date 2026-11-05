"""Initial schema: tenants, users, roster and resource tables.

Revision ID: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('tenants',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('roster_enabled', sa.Boolean(), nullable=False),
    sa.Column('resource_enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('job_roles',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_job_role_name_per_tenant')
    )
    op.create_index(op.f('ix_job_roles_tenant_id'), 'job_roles', ['tenant_id'], unique=False)
    op.create_table('resource_types',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_resource_type_name_per_tenant')
    )
    op.create_index(op.f('ix_resource_types_tenant_id'), 'resource_types', ['tenant_id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=100), nullable=False),
    sa.Column('role', sa.Enum('OWNER', 'MANAGER', 'STAFF', name='role', native_enum=False, length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_table('resources',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('resource_type_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('location', sa.String(length=120), nullable=True),
    sa.Column('status', sa.Enum('AVAILABLE', 'OUT_OF_SERVICE', name='resourcestatus', native_enum=False, length=20), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['resource_type_id'], ['resource_types.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_resource_name_per_tenant')
    )
    op.create_index(op.f('ix_resources_tenant_id'), 'resources', ['tenant_id'], unique=False)
    op.create_table('shift_types',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('end_time', sa.Time(), nullable=False),
    sa.Column('job_role_id', sa.Uuid(), nullable=True),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['job_role_id'], ['job_roles.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_shift_type_name_per_tenant')
    )
    op.create_index(op.f('ix_shift_types_tenant_id'), 'shift_types', ['tenant_id'], unique=False)
    op.create_table('staff_job_roles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('job_role_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['job_role_id'], ['job_roles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'job_role_id')
    )
    op.create_index(op.f('ix_staff_job_roles_tenant_id'), 'staff_job_roles', ['tenant_id'], unique=False)
    op.create_table('bookings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('resource_id', sa.Uuid(), nullable=False),
    sa.Column('start_at', sa.DateTime(), nullable=False),
    sa.Column('end_at', sa.DateTime(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('ACTIVE', 'CANCELLED', name='bookingstatus', native_enum=False, length=20), nullable=False),
    sa.Column('booked_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['booked_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bookings_resource_start', 'bookings', ['tenant_id', 'resource_id', 'start_at'], unique=False)
    op.create_index(op.f('ix_bookings_tenant_id'), 'bookings', ['tenant_id'], unique=False)
    op.create_table('shifts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('start_at', sa.DateTime(), nullable=False),
    sa.Column('end_at', sa.DateTime(), nullable=False),
    sa.Column('shift_type_id', sa.Uuid(), nullable=True),
    sa.Column('job_role_id', sa.Uuid(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['job_role_id'], ['job_roles.id'], ),
    sa.ForeignKeyConstraint(['shift_type_id'], ['shift_types.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shifts_tenant_id'), 'shifts', ['tenant_id'], unique=False)
    op.create_index('ix_shifts_user_start', 'shifts', ['tenant_id', 'user_id', 'start_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_shifts_user_start', table_name='shifts')
    op.drop_index(op.f('ix_shifts_tenant_id'), table_name='shifts')
    op.drop_table('shifts')
    op.drop_index(op.f('ix_bookings_tenant_id'), table_name='bookings')
    op.drop_index('ix_bookings_resource_start', table_name='bookings')
    op.drop_table('bookings')
    op.drop_index(op.f('ix_staff_job_roles_tenant_id'), table_name='staff_job_roles')
    op.drop_table('staff_job_roles')
    op.drop_index(op.f('ix_shift_types_tenant_id'), table_name='shift_types')
    op.drop_table('shift_types')
    op.drop_index(op.f('ix_resources_tenant_id'), table_name='resources')
    op.drop_table('resources')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_resource_types_tenant_id'), table_name='resource_types')
    op.drop_table('resource_types')
    op.drop_index(op.f('ix_job_roles_tenant_id'), table_name='job_roles')
    op.drop_table('job_roles')
    op.drop_table('tenants')
