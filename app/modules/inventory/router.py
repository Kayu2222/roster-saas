import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db import get_db
from app.deps import get_current_user, require_module, require_roles
from app.models import Module, Role, User
from app.modules.inventory import service
from app.modules.inventory.models import Product
from app.modules.inventory.schemas import CountIn, MovementOut, ProductIn, ProductOut, ProductUpdate, ReceiveIn, UseIn

router = APIRouter(prefix="/api/inventory", tags=["Stock"], dependencies=[Depends(require_module(Module.INVENTORY))])

manager_only = require_roles(Role.OWNER, Role.MANAGER)


@router.get("/products", response_model=list[ProductOut])
def list_products(low_only: bool = False, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    products = db.scalars(select(Product).order_by(Product.name)).all()
    return [p for p in products if p.low_stock] if low_only else products


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductIn, caller: User = Depends(manager_only), db: Session = Depends(get_db)):
    return service.create_product(db, body, created_by=caller.id)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, body: ProductUpdate, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    """Rename, change the unit or the reorder level. Stock levels only change through receive, use and count."""
    product = service.get_product(db, product_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(product, field, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, "A product with this name already exists")
    return product


@router.post("/products/{product_id}/receive", response_model=ProductOut)
def receive(product_id: uuid.UUID, body: ReceiveIn, caller: User = Depends(manager_only), db: Session = Depends(get_db)):
    """A delivery came in."""
    return service.receive(db, product_id, body, created_by=caller.id)


@router.post("/products/{product_id}/use", response_model=ProductOut)
def use(product_id: uuid.UUID, body: UseIn, caller: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Anyone in the company can record using stock, optionally for a client. Never goes below zero."""
    return service.use(db, product_id, body, created_by=caller.id)


@router.post("/products/{product_id}/count", response_model=ProductOut)
def count(product_id: uuid.UUID, body: CountIn, caller: User = Depends(manager_only), db: Session = Depends(get_db)):
    """Stocktake correction. Rejected if stock moved between reading and saving."""
    return service.count(db, product_id, body, created_by=caller.id)


@router.get("/movements", response_model=list[MovementOut])
def list_movements(
    product_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    caller: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The stock ledger, newest first. Staff see only the movements they recorded."""
    created_by = caller.id if caller.role == Role.STAFF else None
    return service.movements(db, product_id, client_id, created_by, limit)
