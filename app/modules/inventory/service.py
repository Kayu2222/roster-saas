"""Stock rules.

Every change is ONE atomic UPDATE plus one ledger row, in the same transaction:

    UPDATE products SET on_hand = on_hand - 3
    WHERE id = :id AND on_hand >= 3          -- only if there's enough
    RETURNING on_hand

If two people take the last box at the same instant, the database runs the two
UPDATEs one after the other; the second matches no row (on_hand is now 0) and
gets a clear 409. No read-then-write gap, so no lost updates and no negative stock.
A CHECK constraint (on_hand >= 0) backs this up at the database level.

Stocktakes use compare-and-set instead: "set on_hand to what I counted, but only
if it is still the number I saw". If stock moved in between, the count is rejected.
"""

import uuid

from sqlalchemy import select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import Client
from app.modules.inventory.models import MovementReason, Product, StockMovement
from app.modules.inventory.schemas import CountIn, ProductIn, ReceiveIn, UseIn


def get_product(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise DomainError(404, "Product not found")
    return product


def _check_client(db: Session, client_id: uuid.UUID | None) -> None:
    if client_id is None:
        return
    client = db.get(Client, client_id)
    if client is None:
        raise DomainError(404, "Client not found")
    if not client.is_active:
        raise DomainError(422, f"{client.name} is archived")


def _atomic_change(db: Session, product_id: uuid.UUID, delta: int, *, only_if) -> int | None:
    """Apply on_hand += delta in one statement, guarded by `only_if`. Returns the new on_hand, or None."""
    stmt = (
        update(Product)
        .where(Product.id == product_id, only_if)
        .values(on_hand=Product.on_hand + delta)
        .returning(Product.on_hand)
        .execution_options(synchronize_session=False)
    )
    return db.execute(stmt).scalar_one_or_none()


def _record(db: Session, product_id, change, balance_after, reason, created_by, client_id=None, note=None) -> StockMovement:
    movement = StockMovement(product_id=product_id, change=change, balance_after=balance_after, reason=reason,
                             client_id=client_id, note=note, created_by=created_by)
    db.add(movement)
    try:
        db.commit()
    except IntegrityError:  # CHECK constraint backstop: negative stock or a zero change
        db.rollback()
        raise DomainError(409, "That change would make stock negative")
    return movement


def _fresh(db: Session, product_id: uuid.UUID) -> Product:
    product = get_product(db, product_id)
    db.refresh(product)
    return product


def create_product(db: Session, body: ProductIn, created_by: uuid.UUID) -> Product:
    product = Product(name=body.name.strip(), unit=body.unit.strip(), reorder_level=body.reorder_level, on_hand=body.opening_stock)
    db.add(product)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, "A product with this name already exists")
    if body.opening_stock:
        _record(db, product.id, body.opening_stock, body.opening_stock, MovementReason.RECEIVED, created_by, note="Opening stock")
    else:
        db.commit()
    return product


def receive(db: Session, product_id: uuid.UUID, body: ReceiveIn, created_by: uuid.UUID) -> Product:
    new_balance = _atomic_change(db, product_id, body.quantity, only_if=true())
    if new_balance is None:
        db.rollback()
        get_product(db, product_id)  # 404 if it doesn't exist (or belongs to another company)
    _record(db, product_id, body.quantity, new_balance, MovementReason.RECEIVED, created_by, note=body.note)
    return _fresh(db, product_id)


def use(db: Session, product_id: uuid.UUID, body: UseIn, created_by: uuid.UUID) -> Product:
    _check_client(db, body.client_id)
    new_balance = _atomic_change(db, product_id, -body.quantity, only_if=Product.on_hand >= body.quantity)
    if new_balance is None:
        db.rollback()
        product = _fresh(db, product_id)  # raises 404 if missing
        raise DomainError(409, f"Only {product.on_hand} {product.unit} of {product.name} left")
    _record(db, product_id, -body.quantity, new_balance, MovementReason.USED, created_by,
            client_id=body.client_id, note=body.note)
    return _fresh(db, product_id)


def count(db: Session, product_id: uuid.UUID, body: CountIn, created_by: uuid.UUID) -> Product:
    change = body.counted - body.expected
    new_balance = _atomic_change(db, product_id, change, only_if=Product.on_hand == body.expected)
    if new_balance is None:
        db.rollback()
        product = _fresh(db, product_id)
        raise DomainError(409, f"Stock changed while you were counting (now {product.on_hand} {product.unit}). Count again.")
    if change == 0:
        db.commit()  # count confirmed, nothing to record
    else:
        _record(db, product_id, change, new_balance, MovementReason.COUNTED, created_by, note=body.note)
    return _fresh(db, product_id)


def movements(db: Session, product_id=None, client_id=None, created_by=None, limit: int = 200) -> list[StockMovement]:
    stmt = select(StockMovement)
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if client_id is not None:
        stmt = stmt.where(StockMovement.client_id == client_id)
    if created_by is not None:
        stmt = stmt.where(StockMovement.created_by == created_by)
    return list(db.scalars(stmt.order_by(StockMovement.created_at.desc()).limit(limit)).unique())
