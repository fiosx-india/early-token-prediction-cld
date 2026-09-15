"""
Rolling per-token feature computation.

Keeps a bounded in-memory history of trades/snapshots per token and
derives the feature set the spec calls for. This is intentionally
in-memory + simple (no ML yet) so it's auditable — every number here
maps to one line of the spec's "EARLY BREAKOUT FEATURES" list. A future
ML model would consume this exact feature vector as input rather than
re-deriving it, so results stay comparable across model versions.
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Optional

from app.ingestion.schemas import TradeEvent, TokenLaunchEvent, LiquiditySnapshot, HolderSnapshot


@dataclass
class TokenState:
    token_address: str
    network: str
    launchpad: str
    launch_time: datetime
    creator_address: str
    trades: Deque[TradeEvent] = field(default_factory=lambda: deque(maxlen=5000))
    liquidity_history: Deque[LiquiditySnapshot] = field(default_factory=lambda: deque(maxlen=1000))
    holder_history: Deque[HolderSnapshot] = field(default_factory=lambda: deque(maxlen=1000))
    current_liquidity: float = 0.0
    current_holders: int = 0


@dataclass
class FeatureSnapshot:
    token_address: str
    computed_at: datetime
    age_seconds: float

    buys_per_second: float
    txs_per_second: float
    unique_buyers_per_second: float
    buy_volume: float
    buy_volume_accel: float
    tx_accel: float
    price_velocity: float
    price_accel: float
    liquidity: float
    liquidity_change: float
    holder_growth: float
    holder_growth_accel: float
    market_activity_accel: float
    top_holder_share: Optional[float]
    unique_buyers_total: int


class FeatureEngine:
    """One instance shared across all tracked tokens."""

    def __init__(self, window_seconds: int = 600):
        self.window_seconds = window_seconds
        self._states: dict[str, TokenState] = {}
        # previous-window cache, used to compute acceleration (2nd derivative)
        self._prev_features: dict[str, FeatureSnapshot] = {}

    def register_launch(self, event: TokenLaunchEvent) -> None:
        self._states[event.token_address] = TokenState(
            token_address=event.token_address,
            network=event.network,
            launchpad=event.launchpad,
            launch_time=event.launch_time,
            creator_address=event.creator_address,
            current_liquidity=event.initial_liquidity,
        )

    def ingest_trade(self, event: TradeEvent) -> None:
        state = self._states.get(event.token_address)
        if state is None:
            return  # trade for a token we never saw a launch event for — skip
        state.trades.append(event)

    def ingest_liquidity(self, event: LiquiditySnapshot) -> None:
        state = self._states.get(event.token_address)
        if state is None:
            return
        state.liquidity_history.append(event)
        state.current_liquidity = event.liquidity_quote

    def ingest_holders(self, event: HolderSnapshot) -> None:
        state = self._states.get(event.token_address)
        if state is None:
            return
        state.holder_history.append(event)
        state.current_holders = event.holder_count

    def compute(self, token_address: str, now: datetime) -> Optional[FeatureSnapshot]:
        state = self._states.get(token_address)
        if state is None:
            return None

        age_seconds = max((now - state.launch_time).total_seconds(), 0.001)
        window_start = now.timestamp() - self.window_seconds

        recent_trades = [t for t in state.trades if t.provider_event_ts.timestamp() >= window_start]
        buys = [t for t in recent_trades if t.side == "buy"]
        window_span = min(age_seconds, self.window_seconds) or 1.0

        buys_per_second = len(buys) / window_span
        txs_per_second = len(recent_trades) / window_span
        unique_buyers = {t.wallet_address for t in buys}
        unique_buyers_per_second = len(unique_buyers) / window_span
        buy_volume = sum(t.amount_quote for t in buys)

        # price velocity: slope of price over the recent window
        price_velocity = 0.0
        price_accel = 0.0
        if len(recent_trades) >= 2:
            first, last = recent_trades[0], recent_trades[-1]
            dt = max((last.provider_event_ts - first.provider_event_ts).total_seconds(), 0.001)
            price_velocity = (last.price - first.price) / dt
            if len(recent_trades) >= 3:
                mid = recent_trades[len(recent_trades) // 2]
                dt1 = max((mid.provider_event_ts - first.provider_event_ts).total_seconds(), 0.001)
                dt2 = max((last.provider_event_ts - mid.provider_event_ts).total_seconds(), 0.001)
                v1 = (mid.price - first.price) / dt1
                v2 = (last.price - mid.price) / dt2
                price_accel = (v2 - v1) / max(dt2, 0.001)

        liquidity = state.current_liquidity
        liquidity_change = 0.0
        if len(state.liquidity_history) >= 2:
            liquidity_change = state.liquidity_history[-1].liquidity_quote - state.liquidity_history[-2].liquidity_quote

        holder_growth = 0.0
        if len(state.holder_history) >= 2:
            holder_growth = state.holder_history[-1].holder_count - state.holder_history[-2].holder_count

        prev = self._prev_features.get(token_address)
        buy_volume_accel = (buy_volume - prev.buy_volume) if prev else 0.0
        tx_accel = (txs_per_second - prev.txs_per_second) if prev else 0.0
        holder_growth_accel = (holder_growth - prev.holder_growth) if prev else 0.0
        market_activity_accel = (buy_volume_accel + tx_accel) / 2.0

        top_holder_share = state.holder_history[-1].top_holder_share if state.holder_history else None

        snapshot = FeatureSnapshot(
            token_address=token_address,
            computed_at=now,
            age_seconds=age_seconds,
            buys_per_second=buys_per_second,
            txs_per_second=txs_per_second,
            unique_buyers_per_second=unique_buyers_per_second,
            buy_volume=buy_volume,
            buy_volume_accel=buy_volume_accel,
            tx_accel=tx_accel,
            price_velocity=price_velocity,
            price_accel=price_accel,
            liquidity=liquidity,
            liquidity_change=liquidity_change,
            holder_growth=holder_growth,
            holder_growth_accel=holder_growth_accel,
            market_activity_accel=market_activity_accel,
            top_holder_share=top_holder_share,
            unique_buyers_total=len({t.wallet_address for t in state.trades if t.side == "buy"}),
        )
        self._prev_features[token_address] = snapshot
        return snapshot
