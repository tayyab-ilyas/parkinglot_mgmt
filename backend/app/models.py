"""Imports every model so Base.metadata is complete (Alembic, tests)."""

from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.identity.models import User, user_lots  # noqa: F401
from app.modules.locations.models import City, Level, Lot, Spot  # noqa: F401
from app.modules.parking.models import Ticket  # noqa: F401
from app.modules.payments.models import Payment  # noqa: F401
from app.modules.pricing.models import PricingRule  # noqa: F401
