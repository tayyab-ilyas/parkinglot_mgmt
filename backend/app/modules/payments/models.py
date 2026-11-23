from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Payment(Base):
    # shortcut: only successful payments are stored (failures roll back), so ticket_id is simply unique.
    # Add a status column + partial unique index when a real async gateway needs PENDING rows.
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), unique=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    gateway_ref: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
