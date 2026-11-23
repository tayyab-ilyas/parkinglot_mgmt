import os
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Cookie, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import Role
from app.errors import AppError
from app.modules.identity.models import User, user_lots

SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
COOKIE = "session"
TTL = timedelta(hours=12)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def make_token(user_id: int) -> str:
    return jwt.encode({"sub": str(user_id), "exp": datetime.now(UTC) + TTL}, SECRET, algorithm="HS256")


def current_user(session: str | None = Cookie(None), db: Session = Depends(get_db)) -> User:
    try:
        user_id = int(jwt.decode(session or "", SECRET, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AppError(401, "UNAUTHENTICATED", "Please log in")
    user = db.get(User, user_id)
    if not user or not user.active:
        raise AppError(401, "UNAUTHENTICATED", "Please log in")
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != Role.ADMIN:
        raise AppError(403, "FORBIDDEN", "Admins only")
    return user


def allowed_lot_ids(db: Session, user: User) -> set[int] | None:
    """None means every lot (admin)."""
    if user.role == Role.ADMIN:
        return None
    return set(db.scalars(select(user_lots.c.lot_id).where(user_lots.c.user_id == user.id)))


def ensure_lot_access(db: Session, user: User, lot_id: int) -> None:
    ids = allowed_lot_ids(db, user)
    if ids is not None and lot_id not in ids:
        raise AppError(403, "FORBIDDEN", "You are not assigned to this lot")
