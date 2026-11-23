from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import VehicleType, enum_col


class PricingRule(Base):
    """Immutable once created; superseded or retired by setting retired_at. Money in paise."""

    __tablename__ = "pricing_rules"
    __table_args__ = (
        Index("uq_current_rule", "lot_id", "vehicle_type", unique=True, postgresql_where=text("retired_at IS NULL")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    vehicle_type: Mapped[VehicleType] = mapped_column(enum_col(VehicleType))
    free_minutes: Mapped[int] = mapped_column(default=0)
    hourly_rate: Mapped[int] = mapped_column(BigInteger)
    cap_24h: Mapped[int | None] = mapped_column(BigInteger)
    lost_ticket_fee: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
