import re
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import ensure_lot_access
from app.enums import COMPATIBLE_SIZES, SpotState, TicketStatus, VehicleType
from app.errors import AppError, get_or_404, not_found
from app.modules.audit.models import record
from app.modules.identity.models import User
from app.modules.locations.models import Level, Lot, Spot
from app.modules.payments.gateway import PaymentFailed, gateway
from app.modules.payments.models import Payment
from app.modules.pricing import service as pricing
from app.modules.pricing.models import PricingRule
from app.modules.parking.models import Ticket

CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U

# UPDATE (not just SELECT) so a concurrent claimer re-checks state='FREE' after the row lock is released.
CLAIM_SPOT = text("""
    UPDATE spots SET state = 'OCCUPIED'
    WHERE id = (
        SELECT s.id FROM spots s JOIN levels l ON l.id = s.level_id
        WHERE s.lot_id = :lot_id AND s.state = 'FREE' AND l.active AND s.size = ANY(CAST(:sizes AS varchar[]))
        ORDER BY array_position(CAST(:sizes AS varchar[]), s.size::varchar), l.ordinal, s.code
        FOR UPDATE OF s SKIP LOCKED
        LIMIT 1
    )
    RETURNING id
""")


def normalize_plate(raw: str) -> str:
    plate = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if not 4 <= len(plate) <= 12:
        raise AppError(422, "INVALID_PLATE", "Plate must have 4-12 letters or digits")
    return plate


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))


def _views(db: Session, *where) -> list[dict]:
    q = (
        select(Ticket, Spot.code, Level.name, Lot.currency)
        .join(Spot, Spot.id == Ticket.spot_id)
        .join(Level, Level.id == Spot.level_id)
        .join(Lot, Lot.id == Ticket.lot_id)
        .where(*where)
        .order_by(Ticket.entry_at.desc())
        .limit(200)
    )
    return [
        {
            "code": t.code,
            "lot_id": t.lot_id,
            "plate": t.plate,
            "vehicle_type": t.vehicle_type,
            "spot_code": spot_code,
            "level_name": level_name,
            "currency": currency,
            "entry_at": t.entry_at,
            "exit_at": t.exit_at,
            "status": t.status,
            "lost": t.lost,
        }
        for t, spot_code, level_name, currency in db.execute(q)
    ]


def _lot_full(db: Session, lot: Lot, vehicle_type: VehicleType) -> AppError:
    free_by_size = dict(
        db.execute(
            select(Spot.size, func.count())
            .join(Level, Level.id == Spot.level_id)
            .where(Spot.lot_id == lot.id, Spot.state == SpotState.FREE, Level.active)
            .group_by(Spot.size)
        ).all()
    )
    alternatives = db.execute(
        select(Lot.id, Lot.name, func.count(Spot.id))
        .join(Spot, Spot.lot_id == Lot.id)
        .join(Level, Level.id == Spot.level_id)
        .where(
            Lot.city_id == lot.city_id,
            Lot.id != lot.id,
            Lot.active,
            Level.active,
            Spot.state == SpotState.FREE,
            Spot.size.in_(COMPATIBLE_SIZES[vehicle_type]),
        )
        .group_by(Lot.id, Lot.name)
        .order_by(func.count(Spot.id).desc())
    ).all()
    return AppError(
        409,
        "LOT_FULL",
        f"No free spot for a {vehicle_type.lower()} in {lot.name}",
        {
            "free_by_size": free_by_size,
            "alternatives": [{"lot_id": i, "lot_name": n, "free_spots": c} for i, n, c in alternatives],
        },
    )


def issue_ticket(db: Session, user: User, lot_id: int, raw_plate: str, vehicle_type: VehicleType) -> dict:
    ensure_lot_access(db, user, lot_id)
    plate = normalize_plate(raw_plate)
    lot = get_or_404(db, Lot, lot_id, "lot")
    if not lot.active:
        raise AppError(409, "LOT_INACTIVE", f"{lot.name} is not accepting vehicles")
    rule = pricing.current_rule(db, lot_id, vehicle_type)
    if rule is None:
        raise AppError(409, "NO_PRICING_RULE", f"No active pricing for {vehicle_type} in {lot.name}")
    # Friendly early answer; uq_open_ticket_plate below is the real guarantee.
    if db.scalar(select(Ticket.id).where(Ticket.plate == plate, Ticket.status == TicketStatus.OPEN)):
        raise AppError(409, "VEHICLE_ALREADY_PARKED", f"{plate} already has an open ticket")

    spot_id = db.scalar(CLAIM_SPOT, {"lot_id": lot_id, "sizes": [s.value for s in COMPATIBLE_SIZES[vehicle_type]]})
    if spot_id is None:
        raise _lot_full(db, lot, vehicle_type)

    ticket = Ticket(
        code=new_code(),
        lot_id=lot_id,
        spot_id=spot_id,
        plate=plate,
        vehicle_type=vehicle_type,
        pricing_rule_id=rule.id,
        entry_at=datetime.now(UTC),
        issued_by=user.id,
    )
    db.add(ticket)
    try:
        db.flush()
    except IntegrityError as e:
        if "uq_open_ticket_plate" in str(e.orig):
            raise AppError(409, "VEHICLE_ALREADY_PARKED", f"{plate} already has an open ticket")
        raise
    record(db, user.id, "ticket.issue", "ticket", ticket.id, code=ticket.code, plate=plate, spot_id=spot_id)
    db.commit()
    return _views(db, Ticket.id == ticket.id)[0]


def _find_ticket(db: Session, user: User, code: str, lock: bool = False) -> Ticket:
    q = select(Ticket).where(Ticket.code == code.strip().upper())
    ticket = db.scalar(q.with_for_update() if lock else q)
    if ticket is None:
        raise not_found("ticket")
    ensure_lot_access(db, user, ticket.lot_id)
    return ticket


def get_ticket(db: Session, user: User, code: str, lost: bool = False) -> dict:
    """Ticket plus the fee if it were checked out now."""
    ticket = _find_ticket(db, user, code)
    view = _views(db, Ticket.id == ticket.id)[0]
    now = datetime.now(UTC)
    view["quoted_at"] = now
    rule = db.get(PricingRule, ticket.pricing_rule_id)
    view["rule"] = pricing.rule_view(rule)  # the tariff locked in at entry
    if ticket.status == TicketStatus.OPEN:
        view |= pricing.fee_breakdown(rule, ticket.entry_at, now, lost)
    else:
        view |= pricing.fee_breakdown(rule, ticket.entry_at, ticket.exit_at, ticket.lost)
        view["amount"] = db.scalar(select(Payment.amount).where(Payment.ticket_id == ticket.id))
    return view


def list_tickets(db: Session, user: User, lot_id: int, plate: str | None, status: TicketStatus | None) -> list[dict]:
    ensure_lot_access(db, user, lot_id)
    where = [Ticket.lot_id == lot_id]
    if plate:
        where.append(Ticket.plate.contains(re.sub(r"[^A-Z0-9]", "", plate.upper())))
    if status:
        where.append(Ticket.status == status)
    return _views(db, *where)


def checkout(db: Session, user: User, code: str, expected_amount: int, lost: bool) -> dict:
    """Pay, close the ticket and free the spot in one transaction."""
    ticket = _find_ticket(db, user, code, lock=True)
    if ticket.status != TicketStatus.OPEN:
        raise AppError(409, "TICKET_CLOSED", "This ticket is already checked out")
    now = datetime.now(UTC)
    amount = pricing.calc_fee(db.get(PricingRule, ticket.pricing_rule_id), ticket.entry_at, now, lost)
    if amount != expected_amount:
        raise AppError(409, "FEE_CHANGED", "The fee changed; confirm the new amount", {"amount": amount})

    lot = db.get(Lot, ticket.lot_id)
    # shortcut: gateway is called inside the DB transaction; fine for the in-process dummy.
    # For a real provider: insert a PENDING payment, commit, charge, then finalise in a second transaction.
    try:
        ref = gateway.charge(amount, lot.currency, ticket.code) if amount else None
    except PaymentFailed as e:
        raise AppError(402, "PAYMENT_FAILED", str(e) or "Payment was declined")

    db.add(Payment(ticket_id=ticket.id, amount=amount, gateway_ref=ref, created_by=user.id, created_at=now))
    ticket.status, ticket.exit_at, ticket.lost, ticket.closed_by = TicketStatus.CLOSED, now, lost, user.id
    db.execute(update(Spot).where(Spot.id == ticket.spot_id).values(state=SpotState.FREE))
    record(db, user.id, "ticket.checkout", "ticket", ticket.id, amount=amount, lost=lost, gateway_ref=ref)
    db.commit()
    return {**_views(db, Ticket.id == ticket.id)[0], "amount": amount, "gateway_ref": ref}
