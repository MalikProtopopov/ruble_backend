"""Payment fee calculation — pure business logic."""

from dataclasses import dataclass
from app.domain.constants import PLATFORM_FEE_PERCENT


@dataclass(frozen=True, slots=True)
class FeeBreakdown:
    """Immutable fee calculation result."""
    amount_kopecks: int
    platform_fee_kopecks: int
    acquiring_fee_kopecks: int
    nco_amount_kopecks: int


def calculate_fees(amount_kopecks: int, acquiring_fee_kopecks: int = 0) -> FeeBreakdown:
    """Calculate platform fee and NCO amount from gross payment."""
    platform_fee = amount_kopecks * PLATFORM_FEE_PERCENT // 100
    nco_amount = amount_kopecks - platform_fee - acquiring_fee_kopecks
    return FeeBreakdown(
        amount_kopecks=amount_kopecks,
        platform_fee_kopecks=platform_fee,
        acquiring_fee_kopecks=acquiring_fee_kopecks,
        nco_amount_kopecks=nco_amount,
    )
