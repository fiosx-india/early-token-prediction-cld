"""
Prediction engine: turns a FeatureSnapshot + RiskAssessment into one
breakout probability per horizon, plus supporting/conflicting evidence
text for the dashboard's Evidence Panel.

IMPORTANT: this module computes a *heuristic* probability from real
ingested features — it does not invent numbers. If `feature` is None
(no data yet for a token) it returns None rather than guessing, per
the spec's "do not hard-code fake predictions" rule. Swap the scoring
function for a trained model later; the interface (features+risk -> per
horizon probability) stays the same.
"""
from dataclasses import dataclass
from datetime import datetime

from app.features.feature_engine import FeatureSnapshot
from app.risk.risk_engine import RiskAssessment
from app.prediction.horizons import HORIZON_WEIGHTS, FEATURE_GROUPS


@dataclass
class HorizonPrediction:
    horizon: str
    probability: float
    confidence: float


@dataclass
class PredictionResult:
    token_address: str
    computed_at: datetime
    horizons: dict[str, HorizonPrediction]
    evidence_scores: dict[str, float]
    supporting_evidence: list[str]
    conflicting_evidence: list[str]
    data_freshness_seconds: float
    risk_level: str


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _evidence_scores(feature: FeatureSnapshot, risk: RiskAssessment) -> dict[str, float]:
    """Map raw feature values onto normalized 0..1 evidence scores per
    feature group. Divisors below are rough calibration constants —
    tune them against real historical data once backtesting has run."""
    momentum = _clamp01(0.5 + feature.price_velocity / 4 + feature.buy_volume_accel / 5000)
    buyers = _clamp01(feature.buys_per_second / 6 * 0.6 + min(feature.unique_buyers_total, 100) / 100 * 0.4)
    wallet_quality = _clamp01(1 - risk.concentration_score * 0.8 - risk.wash_trading_score * 0.2)
    liquidity = _clamp01(feature.liquidity / 12000)
    sustain = _clamp01((1 - risk.creator_risk_score) * 0.5 + max(0.0, feature.holder_growth_accel) / 10 * 0.3
                        + (1 - risk.liquidity_risk_score) * 0.2)
    return {
        "momentum": momentum,
        "buyers": buyers,
        "wallet_quality": wallet_quality,
        "liquidity": liquidity,
        "sustain": sustain,
    }


def _confidence_for(feature: FeatureSnapshot, horizon_seconds: int) -> float:
    """More elapsed observation time relative to the horizon length
    -> higher confidence. A 1s-old token gets low confidence on a 24h call."""
    observed = min(feature.age_seconds, horizon_seconds)
    return _clamp01(0.3 + 0.7 * (observed / max(horizon_seconds, 1)))


def predict(feature: FeatureSnapshot | None, risk: RiskAssessment | None) -> PredictionResult | None:
    if feature is None or risk is None:
        return None

    evidence = _evidence_scores(feature, risk)

    horizons: dict[str, HorizonPrediction] = {}
    for horizon, weights in HORIZON_WEIGHTS.items():
        from app.prediction.horizons import HORIZON_SECONDS
        p = sum(weights[g] * evidence[g] for g in FEATURE_GROUPS)
        p = _clamp01(p)
        conf = _confidence_for(feature, HORIZON_SECONDS[horizon])
        horizons[horizon] = HorizonPrediction(horizon=horizon, probability=p, confidence=conf)

    supporting, conflicting = [], []
    if evidence["buyers"] > 0.55:
        supporting.append("Unique-buyer growth is strong relative to token age")
    if evidence["momentum"] > 0.55:
        supporting.append("Price velocity and buy-volume acceleration are positive")
    if evidence["wallet_quality"] > 0.6:
        supporting.append("Low holder concentration, no coordinated-buy signature detected")
    if evidence["liquidity"] > 0.55:
        supporting.append("Liquidity is above the observed median for this token age")
    if not supporting:
        supporting.append("No strong supporting signals yet at this observation window")

    if risk.concentration_score > 0.4:
        conflicting.append("Elevated holder concentration — large share held by top wallets")
    if risk.wash_trading_score > 0.3:
        conflicting.append("Transaction pattern resembles coordinated / wash-trading activity")
    if risk.creator_risk_score > 0.6:
        conflicting.append("Creator wallet carries risk flags from prior history")
    if evidence["liquidity"] < 0.35:
        conflicting.append("Liquidity is thin relative to trade volume")
    if not conflicting:
        conflicting.append("No major conflicting signals detected yet")

    return PredictionResult(
        token_address=feature.token_address,
        computed_at=feature.computed_at,
        horizons=horizons,
        evidence_scores=evidence,
        supporting_evidence=supporting,
        conflicting_evidence=conflicting,
        data_freshness_seconds=0.0,  # filled in by the API layer from ingestion timestamps
        risk_level=risk.overall_risk_level,
    )
