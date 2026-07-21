"""Quality rules for WB funnel CTR report rows and aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app import settings


ZERO_IMPRESSIONS_WITH_CLICKS = "ZERO_IMPRESSIONS_WITH_CLICKS"
CLICKS_EXCEED_IMPRESSIONS = "CLICKS_EXCEED_IMPRESSIONS"
CTR_EXCEEDS_100 = "CTR_EXCEEDS_100"
REPORTED_CTR_MISMATCH = "REPORTED_CTR_MISMATCH"
DELETED_PRODUCT = "DELETED_PRODUCT"
REPORTED_CTR_MISSING = "REPORTED_CTR_MISSING"

DEFAULT_BLOCKING_FLAGS = (
    ZERO_IMPRESSIONS_WITH_CLICKS,
    CLICKS_EXCEED_IMPRESSIONS,
    CTR_EXCEEDS_100,
    REPORTED_CTR_MISMATCH,
    DELETED_PRODUCT,
)


@dataclass(frozen=True)
class FunnelCTRQualityConfig:
    mismatch_tolerance_pp: Decimal
    indicative_impressions: int
    reliable_impressions: int
    high_sample_impressions: int
    recommended_active_days: int


def get_quality_config() -> FunnelCTRQualityConfig:
    return FunnelCTRQualityConfig(
        mismatch_tolerance_pp=Decimal(str(settings.WB_FUNNEL_CTR_MISMATCH_TOLERANCE_PP)),
        indicative_impressions=settings.WB_FUNNEL_CTR_INDICATIVE_IMPRESSIONS,
        reliable_impressions=settings.WB_FUNNEL_CTR_RELIABLE_IMPRESSIONS,
        high_sample_impressions=settings.WB_FUNNEL_CTR_HIGH_SAMPLE_IMPRESSIONS,
        recommended_active_days=settings.WB_FUNNEL_CTR_RECOMMENDED_ACTIVE_DAYS,
    )


def evaluate_daily_quality(
    *,
    impressions: int,
    card_clicks: int,
    reported_ctr: Decimal | None,
    is_deleted: bool,
    config: FunnelCTRQualityConfig | None = None,
) -> tuple[str, list[str]]:
    cfg = config or get_quality_config()
    flags: list[str] = []
    if impressions == 0 and card_clicks > 0:
        flags.append(ZERO_IMPRESSIONS_WITH_CLICKS)
    if card_clicks > impressions:
        flags.append(CLICKS_EXCEED_IMPRESSIONS)
    if reported_ctr is None:
        flags.append(REPORTED_CTR_MISSING)
    else:
        if reported_ctr > Decimal("100"):
            flags.append(CTR_EXCEEDS_100)
        if impressions > 0:
            expected = (Decimal(card_clicks) / Decimal(impressions) * Decimal("100")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
            if abs(reported_ctr - expected) > cfg.mismatch_tolerance_pp:
                flags.append(REPORTED_CTR_MISMATCH)
    if is_deleted:
        flags.append(DELETED_PRODUCT)
    return ("warning" if flags else "ok"), flags


def sample_tier(impressions: int, config: FunnelCTRQualityConfig | None = None) -> str:
    cfg = config or get_quality_config()
    if impressions >= cfg.high_sample_impressions:
        return "high_sample"
    if impressions >= cfg.reliable_impressions:
        return "reliable"
    if impressions >= cfg.indicative_impressions:
        return "indicative"
    return "insufficient"
