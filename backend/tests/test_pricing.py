from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pricing.models import PricingRule
from app.modules.pricing.service import calc_fee

T0 = datetime(2026, 1, 1, tzinfo=UTC)
RULE = PricingRule(free_minutes=10, hourly_rate=4000, cap_24h=30000, lost_ticket_fee=20000)


@pytest.mark.parametrize(
    "minutes, expected",
    [
        (0, 0),
        (10, 0),  # grace period inclusive
        (11, 4000),  # past grace: billed from the start
        (60, 4000),
        (61, 8000),
        (8 * 60, 30000),  # 8h * 40 = 320 -> capped at 300
        (24 * 60, 30000),
        (25 * 60, 34000),  # one day cap + one hour
        (48 * 60 + 1, 64000),
    ],
)
def test_fee(minutes, expected):
    assert calc_fee(RULE, T0, T0 + timedelta(minutes=minutes)) == expected


def test_breakdown_lines_sum_to_total():
    from app.modules.pricing.service import fee_breakdown

    b = fee_breakdown(RULE, T0, T0 + timedelta(hours=25, minutes=30), lost=True)
    assert [line["kind"] for line in b["lines"]] == ["days", "hours", "lost"]
    assert b["amount"] == 30000 + 2 * 4000 + 20000 == sum(line["amount"] for line in b["lines"])
    capped = fee_breakdown(RULE, T0, T0 + timedelta(hours=9))["lines"]
    assert capped[0]["amount"] == 30000 and "cap" in capped[0]["label"]


def test_lost_ticket_adds_fee_even_in_grace():
    assert calc_fee(RULE, T0, T0 + timedelta(minutes=5), lost=True) == 20000


def test_no_cap():
    rule = PricingRule(free_minutes=0, hourly_rate=100, cap_24h=None, lost_ticket_fee=0)
    assert calc_fee(rule, T0, T0 + timedelta(hours=25)) == 2500
