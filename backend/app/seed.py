"""Demo data. Idempotent: does nothing if any user exists.

`python -m app.seed --history 30` also simulates 30 past days of closed tickets for the dashboards."""

import random
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select

import app.models  # noqa: F401
from app.auth import hash_password
from app.db import SessionLocal
from app.enums import COMPATIBLE_SIZES, Role, SpotSize, TicketStatus, VehicleType
from app.modules.identity.models import User, user_lots
from app.modules.locations.models import City, Level, Lot, Spot
from app.modules.parking.models import Ticket
from app.modules.parking.service import new_code
from app.modules.payments.models import Payment
from app.modules.pricing.models import PricingRule
from app.modules.pricing.service import calc_fee

LAYOUT = {SpotSize.SMALL: 4, SpotSize.MEDIUM: 8, SpotSize.LARGE: 2}  # per level
RULES = {  # free_minutes, hourly, cap_24h, lost_fee (paise)
    VehicleType.MOTORCYCLE: (10, 2_000, 15_000, 10_000),
    VehicleType.CAR: (10, 4_000, 30_000, 20_000),
    VehicleType.TRUCK: (0, 10_000, 80_000, 50_000),
}


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            print("seed: users exist, skipping")
            return
        admin = User(username="admin", password_hash=hash_password("admin123"), role=Role.ADMIN)
        attendant = User(username="attendant", password_hash=hash_password("attendant123"), role=Role.ATTENDANT)
        city = City(name="Bengaluru")
        db.add_all([admin, attendant, city])
        db.flush()
        lots = [Lot(city_id=city.id, name=n) for n in ("MG Road", "Koramangala")]
        db.add_all(lots)
        db.flush()
        for lot in lots:
            for ordinal, name in enumerate(("B1", "G")):
                level = Level(lot_id=lot.id, name=name, ordinal=ordinal)
                db.add(level)
                db.flush()
                db.add_all(
                    Spot(lot_id=lot.id, level_id=level.id, code=f"{name}-{size[0]}{n:02d}", size=size)
                    for size, count in LAYOUT.items()
                    for n in range(1, count + 1)
                )
            db.add_all(
                PricingRule(lot_id=lot.id, vehicle_type=vt, free_minutes=f, hourly_rate=h, cap_24h=c, lost_ticket_fee=x)
                for vt, (f, h, c, x) in RULES.items()
            )
        db.execute(insert(user_lots).values(user_id=attendant.id, lot_id=lots[0].id))
        db.commit()
        print("seed: admin/admin123, attendant/attendant123 (MG Road)")


ARRIVALS_BY_HOUR = {7: 2, 8: 5, 9: 7, 10: 5, 11: 4, 12: 4, 13: 5, 14: 3, 15: 3, 16: 4, 17: 6, 18: 7, 19: 5, 20: 3, 21: 2}


def history(days: int) -> None:
    """Closed tickets with payments, priced by the real fee rules. Skips if simulated tickets exist."""
    rnd = random.Random(7)
    with SessionLocal() as db:
        if db.scalar(select(Ticket.id).where(Ticket.plate.like("%SIM%")).limit(1)):
            print("seed: history exists, skipping")
            return
        admin = db.scalar(select(User.id).where(User.role == Role.ADMIN))
        count = 0
        for lot in db.scalars(select(Lot)):
            tz = ZoneInfo(lot.timezone)
            rules = {r.vehicle_type: r for r in db.scalars(select(PricingRule).where(PricingRule.lot_id == lot.id, PricingRule.retired_at.is_(None)))}
            spots = {s: db.scalars(select(Spot.id).where(Spot.lot_id == lot.id, Spot.size == s)).all() for s in SpotSize}
            today = datetime.now(tz).date()
            for d in range(days, 0, -1):
                day = today - timedelta(days=d)
                busy = 1.3 if day.weekday() < 5 else 0.8
                for hour, base in ARRIVALS_BY_HOUR.items():
                    for _ in range(max(0, round(rnd.gauss(base * busy, 1.2)))):
                        vt = rnd.choices(list(VehicleType), weights=[25, 70, 5])[0]
                        sizes = COMPATIBLE_SIZES[vt]
                        size = sizes[0] if rnd.random() < 0.85 or len(sizes) == 1 else sizes[-1]
                        if vt not in rules or not spots[size]:
                            continue
                        entry = datetime.combine(day, time(hour, rnd.randrange(60)), tz)
                        exit_at = entry + timedelta(minutes=max(4, int(rnd.lognormvariate(4.4, 0.7))))
                        lost = rnd.random() < 0.02
                        t = Ticket(
                            code=new_code(), lot_id=lot.id, spot_id=rnd.choice(spots[size]), plate=f"KA{rnd.randrange(1, 60):02d}SIM{count:05d}",
                            vehicle_type=vt, pricing_rule_id=rules[vt].id, entry_at=entry, exit_at=exit_at,
                            status=TicketStatus.CLOSED, lost=lost, issued_by=admin, closed_by=admin,
                        )
                        db.add(t)
                        db.flush()
                        db.add(Payment(ticket_id=t.id, amount=calc_fee(rules[vt], entry, exit_at, lost), created_by=admin, created_at=exit_at))
                        count += 1
        db.commit()
        print(f"seed: {count} simulated past tickets")


if __name__ == "__main__":
    main()
    if "--history" in sys.argv:
        history(int(sys.argv[sys.argv.index("--history") + 1]))
