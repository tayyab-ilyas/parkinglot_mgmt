from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.auth import admin_only, current_user, ensure_lot_access
from app.db import get_db
from app.enums import SpotState
from app.errors import AppError, get_or_404
from app.modules.audit.models import AuditLog
from app.modules.identity.models import User
from app.modules.locations.models import Level, Lot, Spot

router = APIRouter(tags=["reporting"])

REVENUE = text("""
    SELECT (p.created_at AT TIME ZONE l.timezone)::date AS day, SUM(p.amount) AS amount, COUNT(*) AS payments
    FROM payments p
    JOIN tickets t ON t.id = p.ticket_id
    JOIN lots l ON l.id = t.lot_id
    WHERE t.lot_id = :lot_id AND (p.created_at AT TIME ZONE l.timezone)::date BETWEEN :from_date AND :to_date
    GROUP BY 1 ORDER BY 1
""")


# shortcut: analytics scan the lot's tickets in the date window on every call; add a daily rollup table
# when one lot passes ~1M tickets a year.
_LOCAL_DAY = "(CAST(t.entry_at AT TIME ZONE :tz AS date) BETWEEN :from_date AND :to_date)"
_WINDOW = "t.entry_at >= CAST(:from_date AS date) - interval '1 day' AND t.entry_at < CAST(:to_date AS date) + interval '2 day'"

DAILY = text(f"""
    SELECT d.day, COALESCE(e.n, 0) AS entries, COALESCE(x.n, 0) AS exits, COALESCE(r.amount, 0) AS revenue
    FROM (SELECT CAST(g AS date) AS day FROM generate_series(CAST(:from_date AS date), CAST(:to_date AS date), interval '1 day') g) d
    LEFT JOIN (SELECT CAST(t.entry_at AT TIME ZONE :tz AS date) AS day, COUNT(*) AS n FROM tickets t
               WHERE t.lot_id = :lot_id AND {_WINDOW} GROUP BY 1) e ON e.day = d.day
    LEFT JOIN (SELECT CAST(t.exit_at AT TIME ZONE :tz AS date) AS day, COUNT(*) AS n FROM tickets t
               WHERE t.lot_id = :lot_id AND t.exit_at IS NOT NULL AND {_WINDOW.replace('entry_at', 'exit_at')} GROUP BY 1) x ON x.day = d.day
    LEFT JOIN (SELECT CAST(p.created_at AT TIME ZONE :tz AS date) AS day, SUM(p.amount) AS amount FROM payments p
               JOIN tickets t ON t.id = p.ticket_id
               WHERE t.lot_id = :lot_id AND {_WINDOW.replace('t.entry_at', 'p.created_at')} GROUP BY 1) r ON r.day = d.day
    ORDER BY d.day
""")

HOURLY = text(f"""
    SELECT h AS hour, COALESCE(e.n, 0) AS entries
    FROM generate_series(0, 23) h
    LEFT JOIN (SELECT CAST(EXTRACT(HOUR FROM t.entry_at AT TIME ZONE :tz) AS int) AS hr, COUNT(*) AS n FROM tickets t
               WHERE t.lot_id = :lot_id AND {_WINDOW} AND {_LOCAL_DAY} GROUP BY 1) e ON e.hr = h
    ORDER BY h
""")

BY_VEHICLE = text(f"""
    SELECT t.vehicle_type, COUNT(*) AS entries, COUNT(*) FILTER (WHERE t.lost) AS lost,
           COUNT(*) FILTER (WHERE t.exit_at IS NOT NULL) AS stays,
           CAST(AVG(EXTRACT(EPOCH FROM t.exit_at - t.entry_at) / 60) FILTER (WHERE t.exit_at IS NOT NULL) AS int) AS avg_minutes
    FROM tickets t WHERE t.lot_id = :lot_id AND {_WINDOW} AND {_LOCAL_DAY}
    GROUP BY 1
""")

REVENUE_BY_VEHICLE = text(f"""
    SELECT t.vehicle_type, SUM(p.amount) AS revenue FROM payments p JOIN tickets t ON t.id = p.ticket_id
    WHERE t.lot_id = :lot_id AND {_WINDOW.replace('t.entry_at', 'p.created_at')}
      AND CAST(p.created_at AT TIME ZONE :tz AS date) BETWEEN :from_date AND :to_date
    GROUP BY 1
""")

MATRIX = text(f"""
    SELECT t.vehicle_type, s.size AS spot_size, COUNT(*) AS n
    FROM tickets t JOIN spots s ON s.id = t.spot_id
    WHERE t.lot_id = :lot_id AND {{where}}
    GROUP BY 1, 2
""")

OVERVIEW = text("""
    SELECT l.id AS lot_id,
      (SELECT COUNT(*) FROM spots s WHERE s.lot_id = l.id) AS total_spots,
      (SELECT COUNT(*) FROM spots s WHERE s.lot_id = l.id AND s.state = 'OCCUPIED') AS occupied,
      (SELECT COUNT(*) FROM spots s WHERE s.lot_id = l.id AND s.state = 'OUT_OF_SERVICE') AS out_of_service,
      (SELECT COUNT(*) FROM tickets t WHERE t.lot_id = l.id AND t.entry_at > now() - interval '2 day'
         AND CAST(t.entry_at AT TIME ZONE l.timezone AS date) = CAST(now() AT TIME ZONE l.timezone AS date)) AS entries_today,
      (SELECT COALESCE(SUM(p.amount), 0) FROM payments p JOIN tickets t ON t.id = p.ticket_id
         WHERE t.lot_id = l.id AND p.created_at > now() - interval '2 day'
         AND CAST(p.created_at AT TIME ZONE l.timezone AS date) = CAST(now() AT TIME ZONE l.timezone AS date)) AS revenue_today
    FROM lots l ORDER BY l.id
""")


def _range(from_date: date, to_date: date) -> None:
    if to_date < from_date or (to_date - from_date).days > 366:
        raise AppError(422, "INVALID_RANGE", "Pick a range of at most one year, start before end")


@router.get("/lots/{lot_id}/analytics", dependencies=[Depends(admin_only)])
def analytics(lot_id: int, from_date: date, to_date: date, db: Session = Depends(get_db)):
    """Everything in the lot's local days. Entries count by entry time, revenue by payment time."""
    _range(from_date, to_date)
    lot = get_or_404(db, Lot, lot_id, "lot")
    p = {"lot_id": lot_id, "tz": lot.timezone, "from_date": from_date, "to_date": to_date}
    revenue = dict(db.execute(REVENUE_BY_VEHICLE, p).all())
    by_vehicle = [
        {**dict(r), "revenue": revenue.get(r["vehicle_type"], 0)} for r in db.execute(BY_VEHICLE, p).mappings()
    ]
    for vt in set(revenue) - {r["vehicle_type"] for r in by_vehicle}:  # paid in range, entered before it
        by_vehicle.append({"vehicle_type": vt, "entries": 0, "lost": 0, "stays": 0, "avg_minutes": None, "revenue": revenue[vt]})
    matrix = text(MATRIX.text.format(where=f"{_WINDOW} AND {_LOCAL_DAY}"))
    return {
        "daily": [dict(r) for r in db.execute(DAILY, p).mappings()],
        "hourly": [dict(r) for r in db.execute(HOURLY, p).mappings()],
        "by_vehicle": by_vehicle,
        "matrix": [dict(r) for r in db.execute(matrix, p).mappings()],
    }


@router.get("/lots/{lot_id}/parked")
def parked_now(lot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Vehicles parked right now, by vehicle type and the spot size they occupy."""
    ensure_lot_access(db, user, lot_id)
    matrix = text(MATRIX.text.format(where="t.status = 'OPEN'"))
    return [dict(r) for r in db.execute(matrix, {"lot_id": lot_id}).mappings()]


@router.get("/reports/overview", dependencies=[Depends(admin_only)])
def overview(db: Session = Depends(get_db)):
    """One row per lot: capacity, occupancy and today's numbers in the lot's own timezone."""
    return [dict(r) for r in db.execute(OVERVIEW).mappings()]


@router.get("/lots/{lot_id}/occupancy")
def occupancy(lot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_lot_access(db, user, lot_id)
    count = lambda state: func.count().filter(Spot.state == state)  # noqa: E731
    rows = db.execute(
        select(
            Level.id, Level.name, Level.active, Spot.size, func.count(),
            count(SpotState.FREE), count(SpotState.OCCUPIED), count(SpotState.OUT_OF_SERVICE),
        )
        .join(Level, Level.id == Spot.level_id)
        .where(Spot.lot_id == lot_id)
        .group_by(Level.id, Level.name, Level.active, Level.ordinal, Spot.size)
        .order_by(Level.ordinal, Spot.size)
    )
    keys = ("level_id", "level_name", "level_active", "size", "total", "free", "occupied", "out_of_service")
    return [dict(zip(keys, r)) for r in rows]


@router.get("/reports/revenue", dependencies=[Depends(admin_only)])
def revenue(lot_id: int, from_date: date, to_date: date, db: Session = Depends(get_db)):
    """Per local calendar day in the lot's timezone; amounts in minor units."""
    _range(from_date, to_date)
    rows = db.execute(REVENUE, {"lot_id": lot_id, "from_date": from_date, "to_date": to_date}).mappings()
    return [dict(r) for r in rows]


@router.get("/audit-logs", dependencies=[Depends(admin_only)])
def audit_logs(entity: str | None = None, entity_id: int | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))
    if entity:
        q = q.where(AuditLog.entity == entity)
    if entity_id is not None:
        q = q.where(AuditLog.entity_id == entity_id)
    return [
        {"id": a.id, "actor_id": a.actor_id, "action": a.action, "entity": a.entity,
         "entity_id": a.entity_id, "data": a.data, "at": a.at}
        for a in db.scalars(q)
    ]
