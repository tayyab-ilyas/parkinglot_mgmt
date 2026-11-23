from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select, update

from app.db import SessionLocal
from app.enums import Role, SpotSize, SpotState, VehicleType
from app.errors import AppError
from app.modules.identity.models import User
from app.modules.locations.models import Lot, Spot
from app.modules.parking import service
from app.modules.parking.models import Ticket


def lot_id(name: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Lot.id).where(Lot.name == name))


def admin_user(db):
    return db.scalar(select(User).where(User.role == Role.ADMIN))


def try_issue(lot: int, plate: str, vt=VehicleType.CAR) -> str:
    with SessionLocal() as db:
        try:
            return service.issue_ticket(db, admin_user(db), lot, plate, vt)["spot_code"]
        except AppError as e:
            return e.code


def test_parallel_entries_never_share_a_spot():
    lot = lot_id("MG Road")
    with SessionLocal() as db:  # leave exactly 10 car-compatible spots
        ids = db.scalars(select(Spot.id).where(Spot.lot_id == lot, Spot.size.in_([SpotSize.MEDIUM, SpotSize.LARGE])).order_by(Spot.id)).all()
        db.execute(update(Spot).where(Spot.id.in_(ids[10:])).values(state=SpotState.OUT_OF_SERVICE))
        db.commit()

    with ThreadPoolExecutor(10) as pool:
        results = list(pool.map(lambda i: try_issue(lot, f"KA01AB{i:04d}"), range(50)))

    spots = [r for r in results if r != "LOT_FULL"]
    assert len(spots) == 10 and len(set(spots)) == 10
    assert results.count("LOT_FULL") == 40


def test_same_plate_in_parallel_gets_one_ticket():
    lot = lot_id("MG Road")
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: try_issue(lot, "KA 01 AB 1234"), range(8)))
    assert results.count("VEHICLE_ALREADY_PARKED") == 7
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Ticket)) == 1


def test_car_prefers_medium_then_upsizes_to_large():
    lot = lot_id("MG Road")
    with SessionLocal() as db:
        db.execute(update(Spot).where(Spot.lot_id == lot, Spot.size == SpotSize.MEDIUM).values(state=SpotState.OUT_OF_SERVICE))
        db.commit()
    assert "-L" in try_issue(lot, "KA01AA0001")  # seed codes look like B1-L01


def test_lot_full_lists_alternatives(attendant):
    lot = lot_id("MG Road")
    with SessionLocal() as db:
        db.execute(update(Spot).where(Spot.lot_id == lot).values(state=SpotState.OUT_OF_SERVICE))
        db.commit()
    r = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AA0001", "vehicle_type": "CAR"})
    assert r.status_code == 409 and r.json()["code"] == "LOT_FULL"
    assert [a["lot_name"] for a in r.json()["details"]["alternatives"]] == ["Koramangala"]


def test_entry_quote_checkout_flow(attendant, admin):
    lot = lot_id("MG Road")
    r = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "ka-01-ab-1234", "vehicle_type": "CAR"})
    assert r.status_code == 201, r.text
    ticket = r.json()
    assert ticket["plate"] == "KA01AB1234"

    quote = attendant.get(f"/api/tickets/{ticket['code']}").json()
    assert quote["amount"] == 0  # inside grace period

    assert attendant.post(f"/api/tickets/{ticket['code']}/checkout", json={"expected_amount": 999}).json()["code"] == "FEE_CHANGED"
    r = attendant.post(f"/api/tickets/{ticket['code']}/checkout", json={"expected_amount": 0})
    assert r.status_code == 200 and r.json()["status"] == "CLOSED"

    again = attendant.post(f"/api/tickets/{ticket['code']}/checkout", json={"expected_amount": 0})
    assert again.status_code == 409 and again.json()["code"] == "TICKET_CLOSED"

    occ = admin.get(f"/api/lots/{lot}/occupancy").json()
    assert sum(row["occupied"] for row in occ) == 0
    actions = [a["action"] for a in admin.get("/api/audit-logs?entity=ticket").json()]
    assert actions == ["ticket.checkout", "ticket.issue"]


def test_lost_ticket_by_plate(attendant):
    lot = lot_id("MG Road")
    code = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"}).json()["code"]
    [found] = attendant.get(f"/api/lots/{lot}/tickets?plate=ab1234").json()
    assert found["code"] == code
    quote = attendant.get(f"/api/tickets/{code}?lost=true").json()
    assert quote["amount"] == 20000
    r = attendant.post(f"/api/tickets/{code}/checkout", json={"expected_amount": 20000, "lost": True})
    assert r.status_code == 200 and r.json()["lost"] is True


def test_attendant_scoped_to_assigned_lots(attendant, admin):
    other = lot_id("Koramangala")
    assert [lot["name"] for lot in attendant.get("/api/lots").json()] == ["MG Road"]
    r = attendant.post(f"/api/lots/{other}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"})
    assert r.status_code == 403
    code = admin.post(f"/api/lots/{other}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"}).json()["code"]
    assert attendant.get(f"/api/tickets/{code}").status_code == 403
    assert attendant.get("/api/users").status_code == 403


def test_cannot_take_occupied_spot_out_of_service(admin):
    lot = lot_id("MG Road")
    admin.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"})
    with SessionLocal() as db:
        spot = db.scalar(select(Spot.id).where(Spot.state == SpotState.OCCUPIED))
    r = admin.patch(f"/api/spots/{spot}", json={"state": "OUT_OF_SERVICE"})
    assert r.status_code == 409 and r.json()["code"] == "SPOT_OCCUPIED"


def test_new_pricing_rule_supersedes_current(admin):
    lot = lot_id("MG Road")
    r = admin.post(f"/api/lots/{lot}/pricing-rules", json={"vehicle_type": "CAR", "hourly_rate": 5000})
    assert r.status_code == 201
    current = [x for x in admin.get(f"/api/lots/{lot}/pricing-rules").json() if x["vehicle_type"] == "CAR" and x["retired_at"] is None]
    assert [x["hourly_rate"] for x in current] == [5000]


def test_revenue_by_local_day(admin):
    lot = lot_id("MG Road")
    code = admin.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"}).json()["code"]
    admin.post(f"/api/tickets/{code}/checkout", json={"expected_amount": 20000, "lost": True})
    rows = admin.get(f"/api/reports/revenue?lot_id={lot}&from_date=2000-01-01&to_date=2100-01-01")
    assert rows.status_code == 422  # range guard
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    rows = admin.get(f"/api/reports/revenue?lot_id={lot}&from_date={today}&to_date={today}").json()
    assert rows == [{"day": today, "amount": 20000, "payments": 1}]
