from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    ATTENDANT = "ATTENDANT"


class SpotSize(StrEnum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class SpotState(StrEnum):
    FREE = "FREE"
    OCCUPIED = "OCCUPIED"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class VehicleType(StrEnum):
    MOTORCYCLE = "MOTORCYCLE"
    CAR = "CAR"
    TRUCK = "TRUCK"


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


# Preference order: first size is the natural fit, later ones are allowed upsizes.
COMPATIBLE_SIZES: dict[VehicleType, list[SpotSize]] = {
    VehicleType.MOTORCYCLE: [SpotSize.SMALL, SpotSize.MEDIUM],
    VehicleType.CAR: [SpotSize.MEDIUM, SpotSize.LARGE],
    VehicleType.TRUCK: [SpotSize.LARGE],
}


def enum_col(e: type[StrEnum]) -> SAEnum:
    """VARCHAR + CHECK constraint; easier to extend than a native PG enum."""
    return SAEnum(e, native_enum=False, create_constraint=True, length=20, name=f"ck_{e.__name__.lower()}")
