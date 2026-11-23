from datetime import datetime, timedelta, UTC

from sqlalchemy import update

from app import cache
from app.db import SessionLocal
from app.modules.parking.models import Ticket
from test_reporting import mg_road


"""Cache behaviour through real DB sessions and the API. Pure store logic is in test_cache_unit.py."""


def test_only_a_commit_clears_marked_areas():
    cache.get_or_set(("rates", 1), lambda: "cached")
    with SessionLocal() as db:
        cache.mark_write(db, "pricing_rule")
        db.rollback()
    assert cache.get_or_set(("rates", 1), lambda: "fresh") == "cached"
    with SessionLocal() as db:
        cache.mark_write(db, "pricing_rule")
        db.commit()
    assert cache.get_or_set(("rates", 1), lambda: "fresh") == "fresh"


def test_publishing_a_rule_refreshes_the_cached_rate_card(admin):
    lot = mg_road()
    car = lambda: next(r for r in admin.get(f"/api/lots/{lot}/rates").json()["rules"] if r["vehicle_type"] == "CAR")  # noqa: E731
    before = car()
    assert admin.post(f"/api/lots/{lot}/pricing-rules", json={"vehicle_type": "CAR", "hourly_rate": 7700}).status_code == 201
    assert car()["hourly_rate"] == 7700 != before["hourly_rate"]
    assert admin.post(f"/api/pricing-rules/{car()['id']}/retire").status_code == 200
    assert all(r["vehicle_type"] != "CAR" for r in admin.get(f"/api/lots/{lot}/rates").json()["rules"])


def test_cache_endpoint_shows_entries_and_counts(admin, attendant):
    lot = mg_road()
    admin.get(f"/api/lots/{lot}/rates")
    admin.get(f"/api/lots/{lot}/rates")
    view = admin.get("/api/cache").json()
    assert view["areas"]["rates"]["misses"] >= 1 and view["areas"]["rates"]["hits"] >= 1
    assert any(e["key"] == ["rates", lot] and 0 < e["expires_in_s"] <= 300 for e in view["entries"])
    assert attendant.get("/api/cache").status_code == 403


def test_live_reads_follow_entry_and_checkout(attendant):
    lot = mg_road()
    free = lambda: next(x for x in attendant.get("/api/lots").json() if x["id"] == lot)["free_spots"]  # noqa: E731
    occupied = lambda: sum(r["occupied"] for r in attendant.get(f"/api/lots/{lot}/occupancy").json())  # noqa: E731
    open_count = lambda: len(attendant.get(f"/api/lots/{lot}/tickets").json())  # noqa: E731
    f0, o0, n0 = free(), occupied(), open_count()  # now all cached

    code = attendant.post(f"/api/lots/{lot}/tickets", json={"plate": "KA01CC1234", "vehicle_type": "CAR"}).json()["code"]
    assert (free(), occupied(), open_count()) == (f0 - 1, o0 + 1, n0 + 1)
    assert attendant.get(f"/api/tickets/{code}").json()["status"] == "OPEN"

    with SessionLocal() as db:  # back-date entry so the fee is not zero; a direct DB write, so clear by hand
        db.execute(update(Ticket).where(Ticket.code == code).values(entry_at=datetime.now(UTC) - timedelta(hours=3)))
        db.commit()
    cache.clear()
    quote = attendant.get(f"/api/tickets/{code}").json()
    assert quote["amount"] > 0  # the fee is computed per request, never served from the cache

    assert attendant.post(f"/api/tickets/{code}/checkout", json={"expected_amount": quote["amount"]}).status_code == 200
    assert (free(), occupied(), open_count()) == (f0, o0, n0)
    closed = attendant.get(f"/api/tickets/{code}").json()
    assert closed["status"] == "CLOSED" and closed["amount"] == quote["amount"]
