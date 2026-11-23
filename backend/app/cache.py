"""In-process response cache for the API's read endpoints.

How it stays correct:
- Every key starts with an area name ("live", "tickets", ...). The area sets the TTL (TTL below).
- Every write already calls audit.record() inside its transaction. record() calls mark_write(), which notes the
  areas that entity affects (WRITES below); they are cleared right after that transaction commits.
  A rollback clears nothing, because nothing changed.
- A read that started before a clear never stores its result (see _generation), so a slow read can't put old
  data back.
- TTLs are only the backstop for writes made outside the API (seed script, psql).

shortcut: one dict inside one API process. With several uvicorn workers or servers each keeps its own copy
and a commit only clears its own; move to Redis (same get_or_set / invalidate shape) then.
"""

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db import SessionLocal

TTL = {  # seconds an entry may live if nothing clears it first
    "live": 30,  # occupancy, parked mix, lot list with free counts, lots overview
    "tickets": 60,  # ticket lookups and lists; the fee itself is computed fresh on every request
    "reports": 60,  # analytics, revenue: NOT cleared by ticket writes (see WRITES), so they may trail by a minute
    "audit": 30,
    "places": 300,  # cities, levels, spots
    "rates": 300,
    "pricing": 300,
    "users": 300,  # /me, the user list, each user's lot access
}

# Audited entity -> areas its writes make stale. "audit" is always added.
# Tickets leave "reports" alone on purpose: on a busy lot every entry would wipe the heaviest query's cache.
WRITES = {
    "ticket": ("live", "tickets"),
    "spot": ("live", "places"),
    "level": ("live", "places", "tickets"),  # ticket views show the level name
    "lot": ("live", "places", "tickets", "reports"),  # timezone shifts report days; currency shows on tickets
    "city": ("live", "places"),
    "pricing_rule": ("rates", "pricing"),
    "user": ("users",),
}

MAX_ENTRIES = 5_000
_store: dict[tuple, tuple[float, Any]] = {}  # key -> (expires_at, value), insertion-ordered
_lock = threading.Lock()  # sync FastAPI routes run in a thread pool
_generation = 0  # bumped by invalidate(): a value computed before it must not be stored after it
_PENDING = "cache_stale_areas"
_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"hits": 0, "misses": 0, "cleared": 0})  # since start


MISS = object()  # returned by lookup() when the key is not cached (None can be a real cached value)


def lookup(key: tuple) -> tuple[Any, int]:
    """Step 1 of a cached read: (value, token) on a hit, (MISS, token) on a miss.
    Pass the token to store(), so a write that commits in between stops a stale store."""
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] > time.monotonic():
            _stats[key[0]]["hits"] += 1
            return hit[1], _generation
        _stats[key[0]]["misses"] += 1
        return MISS, _generation


def store(key: tuple, value: Any, token: int) -> None:
    """Step 3 of a cached read: keep value for its area's TTL, unless a write committed since lookup().
    value must be plain data (dicts, lists), never ORM objects: they belong to one session and thread."""
    with _lock:
        if token == _generation:
            _make_room()
            _store[key] = (time.monotonic() + TTL[key[0]], value)


def get_or_set(key: tuple, compute: Callable[[], Any]) -> Any:
    """lookup + compute on a miss + store, in one call. Exceptions are not cached."""
    value, token = lookup(key)
    if value is MISS:
        value = compute()  # outside the lock: a slow query must not block other keys
        store(key, value, token)
    return value


def invalidate(*prefix) -> None:
    """Drop every key that starts with prefix, e.g. invalidate("live"). No prefix: everything."""
    global _generation
    with _lock:
        _generation += 1
        if prefix:
            _stats[prefix[0]]["cleared"] += 1
        for k in [k for k in _store if k[: len(prefix)] == prefix]:
            del _store[k]


def clear() -> None:
    invalidate()


def snapshot() -> dict:
    """What the cache holds now (keys and seconds left, not values) plus counts per area since the API started."""
    now = time.monotonic()
    with _lock:
        entries = [{"key": list(k), "expires_in_s": round(exp - now, 1)} for k, (exp, _) in _store.items() if exp > now]
        areas = {a: {"ttl_s": ttl, "entries": 0, **_stats[a]} for a, ttl in TTL.items()}
    for e in entries:
        if e["key"][0] in areas:
            areas[e["key"][0]]["entries"] += 1
    return {"areas": areas, "entries": entries}


def mark_write(db: Session, entity: str) -> None:
    """Called inside a write transaction; the areas are cleared after it commits. Unknown entity: clear all."""
    db.info.setdefault(_PENDING, set()).update(WRITES.get(entity, tuple(TTL)), ("audit",))


@event.listens_for(SessionLocal, "after_commit")
def _after_commit(session: Session) -> None:
    for area in session.info.pop(_PENDING, ()):
        invalidate(area)


@event.listens_for(SessionLocal, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)


def _make_room() -> None:
    now = time.monotonic()
    for k in [k for k, (exp, _) in _store.items() if exp <= now]:
        del _store[k]
    while len(_store) >= MAX_ENTRIES:
        del _store[next(iter(_store))]  # oldest insert first
