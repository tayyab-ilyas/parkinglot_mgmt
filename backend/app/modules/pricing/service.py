from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.enums import VehicleType
from app.errors import get_or_404
from app.modules.audit.models import record
from app.modules.pricing.models import PricingRule

DAY, HOUR = 86_400, 3_600


def fee_breakdown(rule: PricingRule, entry_at: datetime, exit_at: datetime, lost: bool = False) -> dict:
    """Grace period is all-or-nothing; then each started hour is billed, each rolling 24h capped.
    Returns the total plus the lines that make it up, so the UI shows exactly what the server charged."""
    seconds = max(0, int((exit_at - entry_at).total_seconds()))
    lines: list[dict] = []
    if seconds <= rule.free_minutes * 60:
        lines.append({"kind": "grace", "label": f"Within {rule.free_minutes} free minutes", "amount": 0})
    else:
        days, rem = divmod(seconds, DAY)
        day_fee = rule.cap_24h if rule.cap_24h is not None else 24 * rule.hourly_rate
        if days:
            lines.append({"kind": "days", "label": f"{days} × full 24 h", "quantity": days, "amount": days * day_fee})
        if rem:
            hours = -(-rem // HOUR)  # ceil: every started hour
            hours_fee = hours * rule.hourly_rate
            capped = rule.cap_24h is not None and hours_fee > rule.cap_24h
            lines.append({
                "kind": "hours",
                "label": f"{hours} h started" + (" (24 h cap applied)" if capped else ""),
                "quantity": hours,
                "amount": rule.cap_24h if capped else hours_fee,
            })
    if lost:
        lines.append({"kind": "lost", "label": "Lost-ticket fee", "amount": rule.lost_ticket_fee})
    return {"amount": sum(line["amount"] for line in lines), "lines": lines}


def calc_fee(rule: PricingRule, entry_at: datetime, exit_at: datetime, lost: bool = False) -> int:
    return fee_breakdown(rule, entry_at, exit_at, lost)["amount"]


def rule_view(rule: PricingRule) -> dict:
    return {
        "id": rule.id, "vehicle_type": rule.vehicle_type, "free_minutes": rule.free_minutes,
        "hourly_rate": rule.hourly_rate, "cap_24h": rule.cap_24h, "lost_ticket_fee": rule.lost_ticket_fee,
        "created_at": rule.created_at,
    }


def current_rule(db: Session, lot_id: int, vehicle_type: VehicleType) -> PricingRule | None:
    return db.scalar(
        select(PricingRule).where(
            PricingRule.lot_id == lot_id, PricingRule.vehicle_type == vehicle_type, PricingRule.retired_at.is_(None)
        )
    )


def create_rule(db: Session, actor_id: int, lot_id: int, **fields) -> PricingRule:
    """A new rule supersedes the current one for the same lot + vehicle type."""
    now = datetime.now(UTC)
    db.execute(
        update(PricingRule)
        .where(
            PricingRule.lot_id == lot_id,
            PricingRule.vehicle_type == fields["vehicle_type"],
            PricingRule.retired_at.is_(None),
        )
        .values(retired_at=now)
    )
    rule = PricingRule(lot_id=lot_id, created_at=now, **fields)
    db.add(rule)
    db.flush()
    record(db, actor_id, "pricing_rule.create", "pricing_rule", rule.id, lot_id=lot_id, **fields)
    db.commit()
    return rule


def retire_rule(db: Session, actor_id: int, rule_id: int) -> PricingRule:
    rule = get_or_404(db, PricingRule, rule_id, "pricing_rule", lock=True)
    if rule.retired_at is None:
        rule.retired_at = datetime.now(UTC)
        record(db, actor_id, "pricing_rule.retire", "pricing_rule", rule.id)
        db.commit()
    return rule
