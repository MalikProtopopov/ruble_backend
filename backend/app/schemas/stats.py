from datetime import date
from uuid import UUID
from pydantic import BaseModel


class OverviewStatsResponse(BaseModel):
    gmv_kopecks: int
    platform_fee_kopecks: int
    active_subscriptions: int
    total_donors: int
    new_donors_period: int
    retention_30d: float
    retention_90d: float
    period_from: date | None
    period_to: date | None


class CampaignStatsResponse(BaseModel):
    campaign_id: UUID
    campaign_title: str
    collected_amount: int
    donors_count: int
    average_check_kopecks: int
    subscriptions_count: int
    donations_count: int
    offline_payments_amount: int
