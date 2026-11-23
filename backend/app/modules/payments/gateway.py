import uuid
from typing import Protocol


class PaymentFailed(Exception):
    pass


class PaymentGateway(Protocol):
    def charge(self, amount: int, currency: str, reference: str) -> str:
        """Charge `amount` minor units; return the gateway's reference or raise PaymentFailed."""


class DummyGateway:
    def charge(self, amount: int, currency: str, reference: str) -> str:
        return f"dummy-{uuid.uuid4().hex[:12]}"


# Swap point for a real provider.
gateway: PaymentGateway = DummyGateway()
