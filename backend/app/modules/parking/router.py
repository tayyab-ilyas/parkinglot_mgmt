from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.enums import TicketStatus, VehicleType
from app.modules.identity.models import User
from app.modules.parking import service

router = APIRouter(tags=["parking"])


class TicketIn(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    vehicle_type: VehicleType


class CheckoutIn(BaseModel):
    expected_amount: int = Field(ge=0)
    lost: bool = False


@router.post("/lots/{lot_id}/tickets", status_code=201)
def issue_ticket(lot_id: int, body: TicketIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.issue_ticket(db, user, lot_id, body.plate, body.vehicle_type)


@router.get("/lots/{lot_id}/tickets")
def list_tickets(
    lot_id: int,
    plate: str | None = None,
    status: TicketStatus | None = TicketStatus.OPEN,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return service.list_tickets(db, user, lot_id, plate, status)


@router.get("/tickets/{code}")
def get_ticket(code: str, lost: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.get_ticket(db, user, code, lost)


@router.post("/tickets/{code}/checkout")
def checkout(code: str, body: CheckoutIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.checkout(db, user, code, body.expected_amount, body.lost)
