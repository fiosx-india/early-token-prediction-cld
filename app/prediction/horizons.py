"""
Horizon definitions and per-horizon feature weighting.

Per the spec: short horizons (1s-10m) weight momentum/buyer-activity
heavily; long horizons (15m-24h) shift weight toward sustained
volume/liquidity/creator-history. Weights below are a documented
starting point — swap this module for a trained model later without
changing its call signature (weights_for_horizon -> dict[str, float]).
"""
from typing import Literal

HorizonKey = Literal["1s","5s","10s","30s","1m","5m","10m","15m","30m","1h","4h","12h","24h"]

HORIZON_SECONDS: dict[str, int] = {
    "1s": 1, "5s": 5, "10s": 10, "30s": 30,
    "1m": 60, "5m": 300, "10m": 600, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "12h": 43200, "24h": 86400,
}

# Feature groups the weights are expressed over — each maps to a 0..1
# evidence score computed in prediction_engine.py from raw features.
FEATURE_GROUPS = ["momentum", "buyers", "wallet_quality", "liquidity", "sustain"]

# hand-set starting weights: short horizons favor momentum/buyers,
# long horizons favor liquidity/sustain. Rows sum to 1.0.
HORIZON_WEIGHTS: dict[str, dict[str, float]] = {
    "1s":  {"momentum": 0.35, "buyers": 0.25, "wallet_quality": 0.20, "liquidity": 0.10, "sustain": 0.10},
    "5s":  {"momentum": 0.32, "buyers": 0.25, "wallet_quality": 0.20, "liquidity": 0.12, "sustain": 0.11},
    "10s": {"momentum": 0.30, "buyers": 0.24, "wallet_quality": 0.19, "liquidity": 0.13, "sustain": 0.14},
    "30s": {"momentum": 0.27, "buyers": 0.22, "wallet_quality": 0.18, "liquidity": 0.15, "sustain": 0.18},
    "1m":  {"momentum": 0.24, "buyers": 0.20, "wallet_quality": 0.17, "liquidity": 0.16, "sustain": 0.23},
    "5m":  {"momentum": 0.20, "buyers": 0.17, "wallet_quality": 0.15, "liquidity": 0.18, "sustain": 0.30},
    "10m": {"momentum": 0.16, "buyers": 0.14, "wallet_quality": 0.14, "liquidity": 0.19, "sustain": 0.37},
    "15m": {"momentum": 0.12, "buyers": 0.12, "wallet_quality": 0.13, "liquidity": 0.20, "sustain": 0.43},
    "30m": {"momentum": 0.09, "buyers": 0.10, "wallet_quality": 0.11, "liquidity": 0.22, "sustain": 0.48},
    "1h":  {"momentum": 0.06, "buyers": 0.08, "wallet_quality": 0.10, "liquidity": 0.24, "sustain": 0.52},
    "4h":  {"momentum": 0.04, "buyers": 0.06, "wallet_quality": 0.08, "liquidity": 0.26, "sustain": 0.56},
    "12h": {"momentum": 0.03, "buyers": 0.05, "wallet_quality": 0.07, "liquidity": 0.27, "sustain": 0.58},
    "24h": {"momentum": 0.02, "buyers": 0.04, "wallet_quality": 0.06, "liquidity": 0.28, "sustain": 0.60},
}


def weights_for_horizon(horizon: str) -> dict[str, float]:
    return HORIZON_WEIGHTS[horizon]
