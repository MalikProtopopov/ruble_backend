"""Subscription business rules — pure logic."""

from app.domain.constants import ALLOWED_SUBSCRIPTION_AMOUNTS, BILLING_PERIOD_MULTIPLIER


class InvalidSubscriptionAmount(Exception):
    def __init__(self, amount: int):
        super().__init__(f"Amount {amount} not in {sorted(ALLOWED_SUBSCRIPTION_AMOUNTS)}")


def validate_subscription_amount(amount_kopecks: int) -> None:
    if amount_kopecks not in ALLOWED_SUBSCRIPTION_AMOUNTS:
        raise InvalidSubscriptionAmount(amount_kopecks)


def billing_amount(daily_kopecks: int, period: str) -> int:
    """Calculate actual billing amount from daily rate and period."""
    multiplier = BILLING_PERIOD_MULTIPLIER.get(period)
    if multiplier is None:
        raise ValueError(f"Unknown billing period: {period}")
    return daily_kopecks * multiplier
