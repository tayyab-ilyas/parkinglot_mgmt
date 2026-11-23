"""Shows the two parking data layers working: TicketStore (cache) in front of TicketDB (Postgres).
A spy counts how many times the DB layer is actually called."""

import pytest

from app.db import SessionLocal
from app.modules.parking.repository import TicketDB, TicketStore
from test_reporting import mg_road


@pytest.fixture
def db_calls(monkeypatch):
    """Wraps TicketDB.find / TicketDB.search so every real DB read is counted."""
    calls = {"find": 0, "search": 0}
    for name in calls:
        real = getattr(TicketDB, name)

        def spy(self, *args, _real=real, _name=name):
            calls[_name] += 1
            return _real(self, *args)

        monkeypatch.setattr(TicketDB, name, spy)
    return calls


def park(client, plate="KA01AB1234") -> str:
    return client.post(f"/api/lots/{mg_road()}/tickets", json={"plate": plate, "vehicle_type": "CAR"}).json()["code"]


def test_store_reads_the_db_once_then_serves_from_cache(attendant, db_calls):
    code = park(attendant)
    with SessionLocal() as db:
        store = TicketStore(db)
        first = store.find(code)  # miss: goes to Postgres
        second = store.find(code)  # hit: no SQL
        third = store.find(code)
    assert db_calls["find"] == 1
    assert first == second == third and first["status"] == "OPEN"


def test_db_layer_alone_always_queries(attendant):
    code = park(attendant)
    with SessionLocal() as db:
        a, b = TicketDB(db).find(code), TicketDB(db).find(code)  # no cache in this layer
    assert a == b  # same answer, but it ran the SQL twice


def test_a_checkout_commit_makes_the_store_go_back_to_the_db(attendant, db_calls):
    code = park(attendant)
    with SessionLocal() as db:
        assert TicketStore(db).find(code)["status"] == "OPEN"  # DB call 1, now cached
        assert TicketStore(db).find(code)["status"] == "OPEN"  # cache
    assert db_calls["find"] == 1

    attendant.post(f"/api/tickets/{code}/checkout", json={"expected_amount": 0})  # write: commit clears "tickets"

    with SessionLocal() as db:
        assert TicketStore(db).find(code)["status"] == "CLOSED"  # DB call 2: fresh after the write
    assert db_calls["find"] == 2


def test_search_is_cached_per_query_and_cleared_by_a_new_ticket(attendant, db_calls):
    lot = mg_road()
    with SessionLocal() as db:
        assert TicketStore(db).search(lot, None, None) == []  # DB call 1
        assert TicketStore(db).search(lot, None, None) == []  # cache
        TicketStore(db).search(lot, "KA01", None)  # a different query: DB call 2
    assert db_calls["search"] == 2

    park(attendant)

    with SessionLocal() as db:
        assert len(TicketStore(db).search(lot, None, None)) == 1  # DB call 3: the new ticket shows
    assert db_calls["search"] == 3


def test_api_lookup_goes_through_the_store(attendant, db_calls):
    code = park(attendant)
    for _ in range(3):
        assert attendant.get(f"/api/tickets/{code}").status_code == 200
    assert db_calls["find"] == 1  # three HTTP lookups, one DB read
