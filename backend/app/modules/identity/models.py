from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import Role, enum_col


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(enum_col(Role))
    active: Mapped[bool] = mapped_column(default=True)


user_lots = Table(
    "user_lots",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("lot_id", ForeignKey("lots.id"), primary_key=True),
)
