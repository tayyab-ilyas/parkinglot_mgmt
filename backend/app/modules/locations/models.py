from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import SpotSize, SpotState, enum_col


class City(Base):
    __tablename__ = "cities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    active: Mapped[bool] = mapped_column(default=True)


class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (UniqueConstraint("city_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    active: Mapped[bool] = mapped_column(default=True)


class Level(Base):
    __tablename__ = "levels"
    __table_args__ = (UniqueConstraint("lot_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    name: Mapped[str] = mapped_column(String(50))
    ordinal: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)


class Spot(Base):
    __tablename__ = "spots"
    __table_args__ = (UniqueConstraint("lot_id", "code"), Index("ix_spots_claim", "lot_id", "state", "size"))
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))  # denormalised from level for the claim query
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id"))
    code: Mapped[str] = mapped_column(String(20))
    size: Mapped[SpotSize] = mapped_column(enum_col(SpotSize))
    state: Mapped[SpotState] = mapped_column(enum_col(SpotState), default=SpotState.FREE)
