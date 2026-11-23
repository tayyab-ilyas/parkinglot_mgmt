from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app import cache
from app.auth import COOKIE, TTL, admin_only, current_user, hash_password, make_token, verify_password
from app.db import get_db
from app.enums import Role
from app.errors import AppError, get_or_404
from app.modules.audit.models import record
from app.modules.identity.models import User, user_lots

router = APIRouter(tags=["identity"])


class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=72)  # bcrypt limit
    role: Role


class UserPatch(BaseModel):
    password: str | None = Field(None, min_length=8, max_length=72)
    role: Role | None = None
    active: bool | None = None


def _view(db: Session, user: User) -> dict:
    lot_ids = db.scalars(select(user_lots.c.lot_id).where(user_lots.c.user_id == user.id)).all()
    return {"id": user.id, "username": user.username, "role": user.role, "active": user.active, "lot_ids": lot_ids}


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "Wrong username or password")
    response.set_cookie(
        COOKIE, make_token(user.id), max_age=int(TTL.total_seconds()), httponly=True, samesite="strict"
    )
    return _view(db, user)


@router.post("/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE)


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return cache.get_or_set(("users", "me", user.id), lambda: _view(db, user))


@router.get("/users", dependencies=[Depends(admin_only)])
def list_users(db: Session = Depends(get_db)):
    return cache.get_or_set(("users", "list"), lambda: [_view(db, u) for u in db.scalars(select(User).order_by(User.username))])


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    record(db, admin.id, "user.create", "user", user.id, username=user.username, role=user.role)
    db.commit()
    return _view(db, user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = get_or_404(db, User, user_id, "user")
    if user.id == admin.id and (body.active is False or body.role == Role.ATTENDANT):
        raise AppError(409, "SELF_LOCKOUT", "You cannot deactivate or demote yourself")
    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for k, v in changes.items():
        setattr(user, k, v)
    if body.password:
        user.password_hash = hash_password(body.password)
        changes["password_changed"] = True
    record(db, admin.id, "user.update", "user", user.id, **changes)
    db.commit()
    return _view(db, user)


@router.put("/users/{user_id}/lots")
def set_user_lots(user_id: int, lot_ids: list[int], db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = get_or_404(db, User, user_id, "user")
    db.execute(delete(user_lots).where(user_lots.c.user_id == user.id))
    if lot_ids:
        db.execute(insert(user_lots), [{"user_id": user.id, "lot_id": i} for i in set(lot_ids)])
    record(db, admin.id, "user.set_lots", "user", user.id, lot_ids=sorted(set(lot_ids)))
    db.commit()
    return _view(db, user)
