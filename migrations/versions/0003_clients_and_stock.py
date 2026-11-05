"""Clients (people you serve), stock (products + ledger), and bookings linked to a client.

The CHECK constraints are the database-level guarantee that stock never goes negative.

Revision ID: 0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('clients',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clients_name'), 'clients', ['name'], unique=False)
    op.create_index(op.f('ix_clients_tenant_id'), 'clients', ['tenant_id'], unique=False)
    op.create_table('products',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('unit', sa.String(length=30), nullable=False),
    sa.Column('on_hand', sa.Integer(), nullable=False),
    sa.Column('reorder_level', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('on_hand >= 0', name='ck_products_on_hand_not_negative'),
    sa.CheckConstraint('reorder_level >= 0', name='ck_products_reorder_level_not_negative'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_product_name_per_tenant')
    )
    op.create_index(op.f('ix_products_tenant_id'), 'products', ['tenant_id'], unique=False)
    op.create_table('stock_movements',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('change', sa.Integer(), nullable=False),
    sa.Column('balance_after', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Enum('RECEIVED', 'USED', 'COUNTED', name='movementreason', native_enum=False, length=20), nullable=False),
    sa.Column('client_id', sa.Uuid(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('balance_after >= 0', name='ck_stock_movements_balance_not_negative'),
    sa.CheckConstraint('change <> 0', name='ck_stock_movements_change_not_zero'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_movements_client_id'), 'stock_movements', ['client_id'], unique=False)
    op.create_index('ix_stock_movements_product_created', 'stock_movements', ['tenant_id', 'product_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_stock_movements_tenant_id'), 'stock_movements', ['tenant_id'], unique=False)
    op.add_column('bookings', sa.Column('client_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_bookings_client_id'), 'bookings', ['client_id'], unique=False)
    op.create_foreign_key('fk_bookings_client_id_clients', 'bookings', 'clients', ['client_id'], ['id'])
    op.add_column('tenants', sa.Column('inventory_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenants', 'inventory_enabled')
    op.drop_constraint('fk_bookings_client_id_clients', 'bookings', type_='foreignkey')
    op.drop_index(op.f('ix_bookings_client_id'), table_name='bookings')
    op.drop_column('bookings', 'client_id')
    op.drop_index(op.f('ix_stock_movements_tenant_id'), table_name='stock_movements')
    op.drop_index('ix_stock_movements_product_created', table_name='stock_movements')
    op.drop_index(op.f('ix_stock_movements_client_id'), table_name='stock_movements')
    op.drop_table('stock_movements')
    op.drop_index(op.f('ix_products_tenant_id'), table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_clients_tenant_id'), table_name='clients')
    op.drop_index(op.f('ix_clients_name'), table_name='clients')
    op.drop_table('clients')
