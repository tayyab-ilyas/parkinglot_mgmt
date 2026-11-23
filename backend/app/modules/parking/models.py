from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import TicketStatus, VehicleType, enum_col


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        # The core guarantees: one open ticket per spot, one open ticket per plate.
        Index("uq_open_ticket_spot", "spot_id", unique=True, postgresql_where=text("status = 'OPEN'")),
        Index("uq_open_ticket_plate", "plate", unique=True, postgresql_where=text("status = 'OPEN'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("spots.id"))
    plate: Mapped[str] = mapped_column(String(16))
    vehicle_type: Mapped[VehicleType] = mapped_column(enum_col(VehicleType))
    pricing_rule_id: Mapped[int] = mapped_column(ForeignKey("pricing_rules.id"))
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[TicketStatus] = mapped_column(enum_col(TicketStatus), default=TicketStatus.OPEN)
    lost: Mapped[bool] = mapped_column(default=False)
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
