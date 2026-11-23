from datetime import UTC, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app import cache
from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int]
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


def record(db, actor_id: int | None, action: str, entity: str, entity_id: int, **data) -> None:
    """Add to the caller's transaction, so the audit row commits or rolls back with the change.
    Every write passes through here, so this is also where it marks the cached reads it makes stale."""
    cache.mark_write(db, entity)
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id, data=jsonable_encoder(data)))
