"""Unit tests for app/cache.py on its own: no API, no SQL. A fake clock replaces time.monotonic."""

import threading
import time
from types import SimpleNamespace

import pytest

from app import cache


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    cache.clear()
    cache._stats.clear()
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(cache, "time", SimpleNamespace(monotonic=lambda: clock.now))
    return clock


def counter():
    """A compute() that returns 1, 2, 3... so a test can tell a hit from a recompute."""
    calls = []
    return lambda: calls.append(1) or len(calls)


def test_second_read_is_a_hit():
    compute = counter()
    assert cache.get_or_set(("live", 1), compute) == 1
    assert cache.get_or_set(("live", 1), compute) == 1  # not recomputed


def test_different_keys_are_cached_separately():
    compute = counter()
    assert cache.get_or_set(("live", 1), compute) == 1
    assert cache.get_or_set(("live", 2), compute) == 2


def test_entry_expires_after_its_area_ttl(clean_cache):
    compute = counter()
    cache.get_or_set(("live", 1), compute)  # live TTL is 30 s
    clean_cache.now += 29.9
    assert cache.get_or_set(("live", 1), compute) == 1
    clean_cache.now += 0.1
    assert cache.get_or_set(("live", 1), compute) == 2


def test_errors_are_not_cached():
    def boom():
        raise ValueError("db down")
    with pytest.raises(ValueError):
        cache.get_or_set(("live", 1), boom)
    assert cache.get_or_set(("live", 1), lambda: "ok") == "ok"


def test_invalidate_drops_only_keys_with_that_prefix():
    for key in [("live", 1), ("live", 2), ("rates", 1)]:
        cache.get_or_set(key, lambda: "old")
    cache.invalidate("live", 1)
    assert cache.get_or_set(("live", 1), lambda: "new") == "new"
    assert cache.get_or_set(("live", 2), lambda: "new") == "old"
    cache.invalidate("live")
    assert cache.get_or_set(("live", 2), lambda: "new") == "new"
    assert cache.get_or_set(("rates", 1), lambda: "new") == "old"


def test_clear_drops_everything():
    cache.get_or_set(("live", 1), lambda: "old")
    cache.get_or_set(("rates", 1), lambda: "old")
    cache.clear()
    assert cache.snapshot()["entries"] == []


def test_read_that_overlaps_a_write_is_not_stored():
    def slow_read():
        cache.invalidate("live")  # a write commits while this read is still running
        return "old"
    assert cache.get_or_set(("live", 1), slow_read) == "old"  # the caller still gets an answer
    assert cache.get_or_set(("live", 1), lambda: "new") == "new"  # but it was not kept


def test_full_cache_drops_the_oldest_entry(monkeypatch):
    monkeypatch.setattr(cache, "MAX_ENTRIES", 3)
    for i in range(4):
        cache.get_or_set(("live", i), lambda: "v")
    keys = [e["key"] for e in cache.snapshot()["entries"]]
    assert keys == [["live", 1], ["live", 2], ["live", 3]]


def test_expired_entries_are_dropped_before_old_live_ones(clean_cache, monkeypatch):
    monkeypatch.setattr(cache, "MAX_ENTRIES", 2)
    cache.get_or_set(("rates", 1), lambda: "v")  # 300 s
    cache.get_or_set(("live", 1), lambda: "v")  # 30 s
    clean_cache.now += 31  # live expired, rates still valid
    cache.get_or_set(("live", 2), lambda: "v")
    keys = [e["key"] for e in cache.snapshot()["entries"]]
    assert keys == [["rates", 1], ["live", 2]]


def test_mark_write_notes_the_areas_of_that_entity():
    db = SimpleNamespace(info={})
    cache.mark_write(db, "ticket")
    assert db.info[cache._PENDING] == {"live", "tickets", "audit"}
    cache.mark_write(db, "pricing_rule")  # two writes in one transaction add up
    assert db.info[cache._PENDING] == {"live", "tickets", "audit", "rates", "pricing"}


def test_mark_write_for_an_unknown_entity_clears_every_area():
    db = SimpleNamespace(info={})
    cache.mark_write(db, "something_new")
    assert db.info[cache._PENDING] == set(cache.TTL)


def test_every_write_area_has_a_ttl():
    for areas in cache.WRITES.values():
        assert set(areas) <= set(cache.TTL)


def test_snapshot_counts_hits_misses_and_clears(clean_cache):
    cache.get_or_set(("rates", 1), lambda: "v")  # miss
    cache.get_or_set(("rates", 1), lambda: "v")  # hit
    cache.get_or_set(("rates", 1), lambda: "v")  # hit
    cache.invalidate("live")
    clean_cache.now += 10
    snap = cache.snapshot()
    assert snap["areas"]["rates"] | {"ttl_s": 300} == {"ttl_s": 300, "entries": 1, "hits": 2, "misses": 1, "cleared": 0}
    assert snap["areas"]["live"]["cleared"] == 1
    assert snap["entries"] == [{"key": ["rates", 1], "expires_in_s": 290.0}]


def test_snapshot_hides_expired_entries(clean_cache):
    cache.get_or_set(("live", 1), lambda: "v")
    clean_cache.now += 30
    assert cache.snapshot()["entries"] == []


def test_parallel_readers_all_get_the_value_and_store_one_entry(monkeypatch):
    monkeypatch.setattr(cache, "time", time)  # real clock: threads run for real here
    results = []

    def read():
        results.append(cache.get_or_set(("live", "x"), lambda: time.sleep(0.01) or "v"))

    threads = [threading.Thread(target=read) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["v"] * 20
    assert [e["key"] for e in cache.snapshot()["entries"]] == [["live", "x"]]
