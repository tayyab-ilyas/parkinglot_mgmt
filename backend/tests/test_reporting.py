from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from app.db import SessionLocal
from app.enums import SpotSize, SpotState
from app.modules.locations.models import Lot, Spot


def mg_road() -> int:
    with SessionLocal() as db:
        return db.scalar(select(Lot.id).where(Lot.name == "MG Road"))


def today() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()


def test_rate_card_visible_to_attendant(attendant):
    r = attendant.get(f"/api/lots/{mg_road()}/rates").json()
    assert [x["vehicle_type"] for x in r["rules"]] == ["MOTORCYCLE", "CAR", "TRUCK"]
    assert r["compatible_sizes"]["CAR"] == ["MEDIUM", "LARGE"]
    assert attendant.get(f"/api/lots/{mg_road() + 1}/rates").status_code == 403


def test_quote_carries_breakdown_and_locked_rule(attendant):
    code = attendant.post(f"/api/lots/{mg_road()}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"}).json()["code"]
    q = attendant.get(f"/api/tickets/{code}?lost=true").json()
    assert q["rule"]["hourly_rate"] == 4000
    assert [line["kind"] for line in q["lines"]] == ["grace", "lost"] and q["amount"] == 20000


def test_analytics_and_parked_mix(admin):
    lot = mg_road()
    with SessionLocal() as db:  # force a car into a LARGE spot
        db.execute(update(Spot).where(Spot.lot_id == lot, Spot.size == SpotSize.MEDIUM).values(state=SpotState.OUT_OF_SERVICE))
        db.commit()
    car = admin.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"}).json()["code"]
    admin.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01MC0001", "vehicle_type": "MOTORCYCLE"})
    admin.post(f"/api/tickets/{car}/checkout", json={"expected_amount": 20000, "lost": True})

    d = today()
    a = admin.get(f"/api/lots/{lot}/analytics?from_date={d}&to_date={d}").json()
    assert a["daily"] == [{"day": d, "entries": 2, "exits": 1, "revenue": 20000}]
    assert sum(h["entries"] for h in a["hourly"]) == 2 and len(a["hourly"]) == 24
    by = {r["vehicle_type"]: r for r in a["by_vehicle"]}
    assert by["CAR"]["revenue"] == 20000 and by["CAR"]["lost"] == 1 and by["MOTORCYCLE"]["revenue"] == 0
    assert {"vehicle_type": "CAR", "spot_size": "LARGE", "n": 1} in a["matrix"]

    assert admin.get(f"/api/lots/{lot}/parked").json() == [{"vehicle_type": "MOTORCYCLE", "spot_size": "SMALL", "n": 1}]

    ov = {r["lot_id"]: r for r in admin.get("/api/reports/overview").json()}
    assert ov[lot]["entries_today"] == 2 and ov[lot]["revenue_today"] == 20000 and ov[lot]["occupied"] == 1
    assert admin.get(f"/api/lots/{lot}/analytics?from_date={d}&to_date=2000-01-01").status_code == 422


def test_admin_can_add_and_disable_lot(admin, attendant):
    city = admin.get("/api/cities").json()[0]["id"]
    lot = admin.post(f"/api/cities/{city}/lots", json={"name": "Indiranagar"}).json()
    assert lot["timezone"] == "Asia/Kolkata" and lot["active"] is True
    assert admin.patch(f"/api/lots/{mg_road()}", json={"active": False}).json()["active"] is False
    r = attendant.post(f"/api/lots/{mg_road()}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"})
    assert r.status_code == 409 and r.json()["code"] == "LOT_INACTIVE"
