from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cache
from app.auth import admin_only, current_user, ensure_lot_access
from app.db import get_db
from app.enums import COMPATIBLE_SIZES, VehicleType
from app.errors import get_or_404
from app.modules.identity.models import User
from app.modules.locations.models import Lot
from app.modules.pricing import service
from app.modules.pricing.models import PricingRule

router = APIRouter(tags=["pricing"], dependencies=[Depends(admin_only)])
rates_router = APIRouter(tags=["pricing"])


@rates_router.get("/lots/{lot_id}/rates")
def rate_card(lot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The public tariff: current rule per vehicle type and the spot sizes each may use, in preference order."""
    ensure_lot_access(db, user, lot_id)  # outside the cache: access is per user, the card is per lot
    return cache.get_or_set(("rates", lot_id), lambda: _rate_card(db, lot_id))


def _rate_card(db: Session, lot_id: int) -> dict:
    get_or_404(db, Lot, lot_id, "lot")
    rules = db.scalars(
        select(PricingRule).where(PricingRule.lot_id == lot_id, PricingRule.retired_at.is_(None))
    ).all()
    return {
        "rules": [service.rule_view(r) for r in sorted(rules, key=lambda r: list(VehicleType).index(r.vehicle_type))],
        "compatible_sizes": COMPATIBLE_SIZES,
    }


class RuleIn(BaseModel):
    vehicle_type: VehicleType
    free_minutes: int = Field(0, ge=0, le=1440)
    hourly_rate: int = Field(ge=0)  # paise
    cap_24h: int | None = Field(None, ge=0)
    lost_ticket_fee: int = Field(0, ge=0)


class RuleOut(RuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lot_id: int
    created_at: datetime
    retired_at: datetime | None


@router.get("/lots/{lot_id}/pricing-rules", response_model=list[RuleOut])
def list_rules(lot_id: int, db: Session = Depends(get_db)):
    q = select(PricingRule).where(PricingRule.lot_id == lot_id).order_by(PricingRule.created_at.desc())
    return cache.get_or_set(("pricing", lot_id), lambda: [RuleOut.model_validate(r).model_dump() for r in db.scalars(q)])


# Both writes clear "rates" and "pricing" after commit, through audit.record (see app/cache.py).
@router.post("/lots/{lot_id}/pricing-rules", response_model=RuleOut, status_code=201)
def create_rule(lot_id: int, body: RuleIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    get_or_404(db, Lot, lot_id, "lot")
    return service.create_rule(db, user.id, lot_id, **body.model_dump())


@router.post("/pricing-rules/{rule_id}/retire", response_model=RuleOut)
def retire_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return service.retire_rule(db, user.id, rule_id)
