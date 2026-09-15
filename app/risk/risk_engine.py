"""
Risk / manipulation-detection layer, kept separate from the prediction
engine so a token can score "high breakout probability" and "high risk"
at the same time — the dashboard shows both, it never collapses them
into one number.
"""
from dataclasses import dataclass
from typing import Optional

from app.features.feature_engine import FeatureSnapshot


@dataclass
class RiskAssessment:
    token_address: str
    concentration_score: float      # 0 (well distributed) - 1 (concentrated)
    wash_trading_score: float       # 0 (looks organic) - 1 (looks coordinated)
    creator_risk_score: float       # 0 (clean history) - 1 (flagged history)
    liquidity_risk_score: float     # 0 (deep) - 1 (thin)
    overall_risk_level: str         # "low" | "medium" | "high"
    flags: list[str]


def assess(
    feature: FeatureSnapshot,
    creator_history_score: Optional[float] = None,  # 0=risky .. 1=clean, from creator_history table
    top_holder_share: Optional[float] = None,
) -> RiskAssessment:
    flags: list[str] = []

    concentration = top_holder_share if top_holder_share is not None else (feature.top_holder_share or 0.0)
    if concentration > 0.4:
        flags.append("high_holder_concentration")

    # crude wash-trading proxy: very high tx/sec with very few unique buyers
    wash_score = 0.0
    if feature.txs_per_second > 3 and feature.unique_buyers_per_second < 0.3:
        wash_score = min(1.0, feature.txs_per_second / (feature.unique_buyers_per_second + 0.05) / 20)
        flags.append("possible_wash_trading_pattern")

    creator_risk = 1.0 - creator_history_score if creator_history_score is not None else 0.5
    if creator_risk > 0.6:
        flags.append("creator_has_risk_flags")

    liquidity_risk = 1.0 if feature.liquidity < 1000 else max(0.0, 1.0 - feature.liquidity / 15000)
    if feature.liquidity < 1500:
        flags.append("thin_liquidity")

    composite = (concentration * 0.3 + wash_score * 0.25 + creator_risk * 0.25 + liquidity_risk * 0.2)
    level = "high" if composite > 0.6 else ("medium" if composite > 0.3 else "low")

    return RiskAssessment(
        token_address=feature.token_address,
        concentration_score=concentration,
        wash_trading_score=wash_score,
        creator_risk_score=creator_risk,
        liquidity_risk_score=liquidity_risk,
        overall_risk_level=level,
        flags=flags,
    )
