from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import admin_only, allowed_lot_ids, current_user
from app.db import get_db
from app.enums import SpotSize, SpotState
from app.errors import AppError, get_or_404
from app.modules.audit.models import record
from app.modules.identity.models import User
from app.modules.locations.models import City, Level, Lot, Spot

# CRUD is simple enough that it lives in the router; every write is audited in the same transaction.
router = APIRouter(tags=["locations"])
admin = [Depends(admin_only)]


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CityIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CityPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    active: bool | None = None


class CityOut(Orm):
    id: int
    name: str
    active: bool


class LotPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    timezone: str | None = None
    active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def valid_tz(cls, v):
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("unknown timezone")
        return v


class LotIn(LotPatch):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = "Asia/Kolkata"
    currency: str = Field("INR", pattern="^[A-Z]{3}$")


class LotOut(Orm):
    id: int
    city_id: int
    name: str
    timezone: str
    currency: str
    active: bool


class LevelIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    ordinal: int = 0


class LevelPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    ordinal: int | None = None
    active: bool | None = None


class LevelOut(Orm):
    id: int
    lot_id: int
    name: str
    ordinal: int
    active: bool


class SpotsIn(BaseModel):
    size: SpotSize
    count: int = Field(ge=1, le=500)
    prefix: str = Field(min_length=1, max_length=10, pattern="^[A-Za-z0-9-]+$")
    start: int = Field(1, ge=0)


class SpotPatch(BaseModel):
    state: SpotState


class SpotOut(Orm):
    id: int
    lot_id: int
    level_id: int
    code: str
    size: SpotSize
    state: SpotState


def _patch(db: Session, user: User, obj, entity: str, body: BaseModel):
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(obj, k, v)
    record(db, user.id, f"{entity}.update", entity, obj.id, **changes)
    db.commit()
    return obj


def _create(db: Session, user: User, obj, entity: str):
    db.add(obj)
    db.flush()
    record(db, user.id, f"{entity}.create", entity, obj.id, **{c.key: getattr(obj, c.key) for c in obj.__table__.c})
    db.commit()
    return obj


# --- Cities ---
@router.get("/cities", response_model=list[CityOut], dependencies=admin)
def list_cities(db: Session = Depends(get_db)):
    return db.scalars(select(City).order_by(City.name)).all()


@router.post("/cities", response_model=CityOut, status_code=201)
def create_city(body: CityIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return _create(db, user, City(name=body.name), "city")


@router.patch("/cities/{city_id}", response_model=CityOut)
def update_city(city_id: int, body: CityPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return _patch(db, user, get_or_404(db, City, city_id, "city"), "city", body)


# --- Lots ---
@router.get("/lots")
def list_lots(city_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Lots the caller may work in, with live free-spot counts."""
    free = (
        select(Spot.lot_id, func.count().label("free"))
        .join(Level, Level.id == Spot.level_id)
        .where(Spot.state == SpotState.FREE, Level.active)
        .group_by(Spot.lot_id)
        .subquery()
    )
    q = (
        select(Lot, City.name, func.coalesce(free.c.free, 0))
        .join(City, City.id == Lot.city_id)
        .outerjoin(free, free.c.lot_id == Lot.id)
        .order_by(City.name, Lot.name)
    )
    if city_id is not None:
        q = q.where(Lot.city_id == city_id)
    ids = allowed_lot_ids(db, user)
    if ids is not None:
        q = q.where(Lot.id.in_(ids))
    return [
        {**LotOut.model_validate(lot).model_dump(), "city_name": city, "free_spots": n}
        for lot, city, n in db.execute(q)
    ]


@router.post("/cities/{city_id}/lots", response_model=LotOut, status_code=201)
def create_lot(city_id: int, body: LotIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    get_or_404(db, City, city_id, "city")
    return _create(db, user, Lot(city_id=city_id, **body.model_dump(exclude={"active"})), "lot")


@router.patch("/lots/{lot_id}", response_model=LotOut)
def update_lot(lot_id: int, body: LotPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return _patch(db, user, get_or_404(db, Lot, lot_id, "lot"), "lot", body)


# --- Levels ---
@router.get("/lots/{lot_id}/levels", response_model=list[LevelOut], dependencies=admin)
def list_levels(lot_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(Level).where(Level.lot_id == lot_id).order_by(Level.ordinal)).all()


@router.post("/lots/{lot_id}/levels", response_model=LevelOut, status_code=201)
def create_level(lot_id: int, body: LevelIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    get_or_404(db, Lot, lot_id, "lot")
    return _create(db, user, Level(lot_id=lot_id, **body.model_dump()), "level")


@router.patch("/levels/{level_id}", response_model=LevelOut)
def update_level(level_id: int, body: LevelPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return _patch(db, user, get_or_404(db, Level, level_id, "level"), "level", body)


# --- Spots ---
@router.get("/levels/{level_id}/spots", response_model=list[SpotOut], dependencies=admin)
def list_spots(level_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(Spot).where(Spot.level_id == level_id).order_by(Spot.code)).all()


@router.post("/levels/{level_id}/spots", response_model=list[SpotOut], status_code=201)
def create_spots(level_id: int, body: SpotsIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    level = get_or_404(db, Level, level_id, "level")
    spots = [
        Spot(lot_id=level.lot_id, level_id=level.id, code=f"{body.prefix.upper()}{n:03d}", size=body.size)
        for n in range(body.start, body.start + body.count)
    ]
    db.add_all(spots)
    db.flush()
    record(db, user.id, "spots.create", "level", level.id, **body.model_dump())
    db.commit()
    return spots


@router.patch("/spots/{spot_id}", response_model=SpotOut)
def update_spot(spot_id: int, body: SpotPatch, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if body.state == SpotState.OCCUPIED:
        raise AppError(422, "INVALID_STATE", "Spots become occupied only through ticket entry")
    # Conditional UPDATE: waits on a concurrent claim's row lock, then sees OCCUPIED and changes nothing.
    changed = db.scalar(
        update(Spot)
        .where(Spot.id == spot_id, Spot.state != SpotState.OCCUPIED)
        .values(state=body.state)
        .returning(Spot.id)
    )
    if changed is None:
        get_or_404(db, Spot, spot_id, "spot")
        raise AppError(409, "SPOT_OCCUPIED", "Spot is occupied; check the vehicle out first")
    record(db, user.id, "spot.update", "spot", spot_id, state=body.state)
    db.commit()
    return db.get(Spot, spot_id, populate_existing=True)
