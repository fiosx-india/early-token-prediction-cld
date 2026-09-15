"""
Common event schema every adapter normalizes into.
Nothing downstream (feature engine, prediction engine, DB) ever
looks at a provider-specific payload shape again after this point.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TokenLaunchEvent:
    """Emitted once, when a new token is first detected on a launchpad."""
    token_address: str
    network: str            # "solana" | "bsc"
    launchpad: str           # "pump.fun" | "four.meme" | "flap"
    name: str
    symbol: str
    creator_address: str
    launch_time: datetime
    initial_liquidity: float
    provider_event_ts: datetime   # timestamp the provider attached to the event
    ingested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TradeEvent:
    """Emitted for every buy/sell against a tracked token."""
    token_address: str
    network: str
    side: str                # "buy" | "sell"
    wallet_address: str
    amount_base: float        # amount of the token traded
    amount_quote: float       # amount of SOL/BNB (or stable) traded
    price: float
    tx_hash: str
    provider_event_ts: datetime
    ingested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LiquiditySnapshot:
    token_address: str
    network: str
    liquidity_quote: float
    provider_event_ts: datetime
    ingested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class HolderSnapshot:
    token_address: str
    network: str
    holder_count: int
    top_holder_share: Optional[float] = None
    provider_event_ts: datetime = field(default_factory=datetime.utcnow)
    ingested_at: datetime = field(default_factory=datetime.utcnow)
