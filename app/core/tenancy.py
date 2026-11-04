"""Automatic tenant isolation.

Every model that inherits TenantScoped gets two guarantees, enforced here in
one place instead of in every query:

1. Reads:  every SELECT is automatically filtered to the current tenant.
2. Writes: new rows get the current tenant_id, and a row can never be
           saved under another tenant's id.

The current tenant is stored on the DB session (session.info["tenant_id"]),
set once per request after the JWT is verified (see app/deps.py).

If code queries tenant data WITHOUT a tenant set, we raise an error instead of
silently returning every company's data. The only allowed exception is an
explicit opt-out: .execution_options(bypass_tenant=True), used by login.
"""

import uuid

from sqlalchemy import ForeignKey, Uuid, event
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, declared_attr, mapped_column, with_loader_criteria

TENANT_KEY = "tenant_id"


class TenantContextMissing(RuntimeError):
    """Raised when tenant data is queried without a tenant context."""


class TenantScoped:
    """Mixin: adds tenant_id and opts the model into automatic isolation."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)


def set_tenant(session: Session, tenant_id: uuid.UUID) -> None:
    session.info[TENANT_KEY] = tenant_id


def get_tenant(session: Session) -> uuid.UUID | None:
    return session.info.get(TENANT_KEY)


def _touches_tenant_data(state: ORMExecuteState) -> bool:
    for mapper in state.all_mappers:
        if issubclass(mapper.class_, TenantScoped):
            return True
    return False


@event.listens_for(Session, "do_orm_execute")
def _filter_reads(state: ORMExecuteState) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.execution_options.get("bypass_tenant"):
        return
    if not _touches_tenant_data(state):
        return

    tenant_id = get_tenant(state.session)
    if tenant_id is None:
        raise TenantContextMissing(
            "Tenant data queried without a tenant context. "
            "Authenticate the request, or use execution_options(bypass_tenant=True) on purpose."
        )

    state.statement = state.statement.options(
        with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tenant_id, include_aliases=True)
    )


@event.listens_for(Session, "before_flush")
def _stamp_writes(session: Session, flush_context, instances) -> None:
    tenant_id = get_tenant(session)
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, TenantScoped):
            continue
        if tenant_id is None:
            raise TenantContextMissing(f"Cannot save {type(obj).__name__} without a tenant context.")
        if obj.tenant_id is None:
            obj.tenant_id = tenant_id
        elif obj.tenant_id != tenant_id:
            raise PermissionError(f"Refusing to save {type(obj).__name__} under another tenant.")
