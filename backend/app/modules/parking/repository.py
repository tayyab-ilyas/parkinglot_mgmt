"""Ticket data access for the parking module, in two layers:

    service.py ──reads──► TicketStore ──cache miss──► TicketDB ──► Postgres
               ──writes / locks──────────────────────► TicketDB ──► Postgres

TicketDB     talks to Postgres only and knows nothing about caching.
TicketStore  is what the service reads through: the cache first, TicketDB only on a miss.

Writes (claiming a spot, checkout) never go through TicketStore: they need live rows and row locks.
When they commit, audit.record -> cache.mark_write clears the cached reads (see app/cache.py).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cache
from app.enums import TicketStatus
from app.errors import not_found
from app.modules.locations.models import Level, Lot, Spot
from app.modules.parking.models import Ticket
from app.modules.payments.models import Payment
from app.modules.pricing import service as pricing
from app.modules.pricing.models import PricingRule


class TicketDB:
    """Postgres only. Every method here runs SQL."""

    def __init__(self, db: Session):
        self.db = db

    def views(self, *where) -> list[dict]:
        q = (
            select(Ticket, Spot.code, Level.name, Lot.currency)
            .join(Spot, Spot.id == Ticket.spot_id)
            .join(Level, Level.id == Spot.level_id)
            .join(Lot, Lot.id == Ticket.lot_id)
            .where(*where)
            .order_by(Ticket.entry_at.desc())
            .limit(200)
        )
        return [
            {
                "code": t.code,
                "lot_id": t.lot_id,
                "plate": t.plate,
                "vehicle_type": t.vehicle_type,
                "spot_code": spot_code,
                "level_name": level_name,
                "currency": currency,
                "entry_at": t.entry_at,
                "exit_at": t.exit_at,
                "status": t.status,
                "lost": t.lost,
            }
            for t, spot_code, level_name, currency in self.db.execute(q)
        ]

    def view(self, ticket_id: int) -> dict:
        return self.views(Ticket.id == ticket_id)[0]

    def find(self, code: str) -> dict:
        """Everything about a ticket except the live fee (that depends on the clock, so it is never stored)."""
        ticket = self.db.scalar(select(Ticket).where(Ticket.code == code))
        if ticket is None:
            raise not_found("ticket")
        view = self.view(ticket.id)
        view["rule"] = pricing.rule_view(self.db.get(PricingRule, ticket.pricing_rule_id))  # tariff locked in at entry
        if ticket.status != TicketStatus.OPEN:
            view["paid"] = self.db.scalar(select(Payment.amount).where(Payment.ticket_id == ticket.id))
        return view

    def search(self, lot_id: int, plate: str | None, status: TicketStatus | None) -> list[dict]:
        where = [Ticket.lot_id == lot_id]
        if plate is not None:
            where.append(Ticket.plate.contains(plate))
        if status:
            where.append(Ticket.status == status)
        return self.views(*where)

    def lock(self, code: str) -> Ticket:
        """The ticket row, locked until this transaction ends. For checkout: never cached."""
        ticket = self.db.scalar(select(Ticket).where(Ticket.code == code).with_for_update())
        if ticket is None:
            raise not_found("ticket")
        return ticket


class TicketStore:
    """Read-through cache in front of TicketDB. Same answers as TicketDB, fewer queries."""

    def __init__(self, db: Session):
        self.source = TicketDB(db)

    def find(self, code: str) -> dict:
        key = ("tickets", "one", code)

        # 1. Cache: look for this ticket in memory.
        ticket, token = cache.lookup(key)
        if ticket is not cache.MISS:
            return ticket  # cache hit: answered without touching Postgres

        # 2. Database: not in the cache, so read it from Postgres.
        ticket = self.source.find(code)

        # 3. Cache: keep it, so the next lookup is a hit (until a write commits or the TTL runs out).
        cache.store(key, ticket, token)
        return ticket

    def search(self, lot_id: int, plate: str | None, status: TicketStatus | None) -> list[dict]:
        key = ("tickets", "list", lot_id, plate, status)

        # 1. Cache
        tickets, token = cache.lookup(key)
        if tickets is not cache.MISS:
            return tickets

        # 2. Database
        tickets = self.source.search(lot_id, plate, status)

        # 3. Cache
        cache.store(key, tickets, token)
        return tickets
