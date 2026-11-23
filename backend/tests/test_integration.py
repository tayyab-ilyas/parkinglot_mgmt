"""Integration tests: real HTTP calls through the FastAPI app into a real Postgres database, across modules.
Each test starts from a freshly seeded database (conftest.py)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from app import cache
from app.db import SessionLocal
from app.main import app
from app.modules.parking.models import Ticket
from conftest import login
from test_reporting import mg_road, today


def backdate(code: str, minutes: int) -> None:
    """Pretend the car came in `minutes` ago. A direct DB write skips the app, so clear the cache by hand."""
    with SessionLocal() as db:
        db.execute(update(Ticket).where(Ticket.code == code).values(entry_at=datetime.now(UTC) - timedelta(minutes=minutes)))
        db.commit()
    cache.clear()


def test_new_lot_from_setup_to_paid_exit(admin):
    # Admin builds a lot from nothing: city -> lot -> level -> spots -> pricing.
    city = admin.post("/api/cities", json={"name": "Pune"}).json()
    lot = admin.post(f"/api/cities/{city['id']}/lots", json={"name": "FC Road"}).json()
    level = admin.post(f"/api/lots/{lot['id']}/levels", json={"name": "G", "ordinal": 0}).json()
    spots = admin.post(f"/api/levels/{level['id']}/spots", json={"size": "MEDIUM", "count": 2, "prefix": "A"}).json()
    assert [s["code"] for s in spots] == ["A001", "A002"]
    rule = admin.post(f"/api/lots/{lot['id']}/pricing-rules", json={"vehicle_type": "CAR", "hourly_rate": 5000, "free_minutes": 0})
    assert rule.status_code == 201

    # Admin hires an attendant for that lot only.
    user = admin.post("/api/users", json={"username": "pune_desk", "password": "pune-pass-1", "role": "ATTENDANT"}).json()
    admin.put(f"/api/users/{user['id']}/lots", json=[lot["id"]])
    desk = login("pune_desk", "pune-pass-1")
    assert [x["name"] for x in desk.get("/api/lots").json()] == ["FC Road"]

    # A car parks for just under 2 hours, then pays.
    ticket = desk.post(f"/api/lots/{lot['id']}/tickets", json={"plate": "MH12 AB 1234", "vehicle_type": "CAR"}).json()
    assert ticket["spot_code"] == "A001" and ticket["plate"] == "MH12AB1234"
    backdate(ticket["code"], 119)
    quote = desk.get(f"/api/tickets/{ticket['code']}").json()
    assert quote["amount"] == 10000  # 2 started hours x 5000
    paid = desk.post(f"/api/tickets/{ticket['code']}/checkout", json={"expected_amount": 10000})
    assert paid.status_code == 200 and paid.json()["status"] == "CLOSED"

    # Admin sees it everywhere: occupancy, revenue, audit trail.
    occ = admin.get(f"/api/lots/{lot['id']}/occupancy").json()
    assert sum(r["occupied"] for r in occ) == 0 and sum(r["free"] for r in occ) == 2
    revenue = admin.get(f"/api/reports/revenue?lot_id={lot['id']}&from_date={today()}&to_date={today()}").json()
    assert revenue == [{"day": today(), "amount": 10000, "payments": 1}]
    actions = [a["action"] for a in admin.get("/api/audit-logs").json()]  # newest first
    assert actions[:2] == ["ticket.checkout", "ticket.issue"]
    setup = {"city.create", "lot.create", "level.create", "spots.create", "pricing_rule.create", "user.create", "user.set_lots"}
    assert setup <= set(actions)


def test_login_logout_and_protected_routes():
    anon = TestClient(app)
    assert anon.get("/api/me").status_code == 401
    bad = anon.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401 and bad.json()["code"] == "INVALID_CREDENTIALS"

    user = login("attendant", "attendant123")
    assert user.get("/api/me").json()["role"] == "ATTENDANT"
    assert user.post("/api/auth/logout").status_code == 204
    assert user.get("/api/me").status_code == 401


def test_deactivated_user_is_locked_out_at_once(admin, attendant):
    me = attendant.get("/api/me").json()
    assert admin.patch(f"/api/users/{me['id']}", json={"active": False}).status_code == 200
    assert attendant.get("/api/me").status_code == 401  # same session cookie, rejected on the next call
    assert TestClient(app).post("/api/auth/login", json={"username": "attendant", "password": "attendant123"}).status_code == 401


def test_moving_an_attendant_to_another_lot_applies_immediately(admin, attendant):
    other = next(x["id"] for x in admin.get("/api/lots").json() if x["id"] != mg_road())
    plate = {"plate": "KA01AB1234", "vehicle_type": "CAR"}
    assert attendant.get(f"/api/lots/{mg_road()}/occupancy").status_code == 200  # access now cached
    me = attendant.get("/api/me").json()
    admin.put(f"/api/users/{me['id']}/lots", json=[other])
    assert attendant.post(f"/api/lots/{mg_road()}/tickets", json=plate).status_code == 403
    assert attendant.post(f"/api/lots/{other}/tickets", json=plate).status_code == 201


def test_bad_input_is_rejected_with_a_clear_error(attendant, admin):
    lot = mg_road()
    r = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "AB", "vehicle_type": "CAR"})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_PLATE"
    r = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "BUS"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    r = attendant.get("/api/tickets/NOSUCHCODE")
    assert r.status_code == 404 and r.json()["code"] == "TICKET_NOT_FOUND"
    r = admin.patch("/api/spots/1", json={"state": "OCCUPIED"})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_STATE"
    assert set(r.json()) == {"code", "message", "details"}  # every error has the same shape


def test_entry_refused_when_no_price_is_set(admin, attendant):
    lot = mg_road()
    car_rule = next(r for r in admin.get(f"/api/lots/{lot}/rates").json()["rules"] if r["vehicle_type"] == "CAR")
    admin.post(f"/api/pricing-rules/{car_rule['id']}/retire")
    r = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"})
    assert r.status_code == 409 and r.json()["code"] == "NO_PRICING_RULE"


def test_closed_level_is_skipped_and_reopened_level_is_used(admin, attendant):
    lot = mg_road()
    levels = admin.get(f"/api/lots/{lot}/levels").json()
    first, second = levels[0], levels[1]
    admin.patch(f"/api/levels/{first['id']}", json={"active": False})
    t = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB0001", "vehicle_type": "CAR"}).json()
    assert t["level_name"] == second["name"]
    admin.patch(f"/api/levels/{first['id']}", json={"active": True})
    t = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB0002", "vehicle_type": "CAR"}).json()
    assert t["level_name"] == first["name"]


def test_price_change_does_not_touch_cars_already_parked(admin, attendant):
    lot = mg_road()
    code = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB1234", "vehicle_type": "CAR"}).json()["code"]
    backdate(code, 59)
    admin.post(f"/api/lots/{lot}/pricing-rules", json={"vehicle_type": "CAR", "hourly_rate": 99900})
    quote = attendant.get(f"/api/tickets/{code}").json()
    assert quote["rule"]["hourly_rate"] == 4000 and quote["amount"] == 4000  # tariff locked in at entry
    new = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01AB9999", "vehicle_type": "CAR"}).json()["code"]
    assert attendant.get(f"/api/tickets/{new}").json()["rule"]["hourly_rate"] == 99900
