"""
Common interface every launchpad/provider adapter must implement.
This is the seam that lets us add Ethereum, Base, or a new launchpad
later without touching ingestion, features, prediction, or the API.
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Union

from app.ingestion.schemas import (
    TokenLaunchEvent,
    TradeEvent,
    LiquiditySnapshot,
    HolderSnapshot,
)

StreamEvent = Union[TokenLaunchEvent, TradeEvent, LiquiditySnapshot, HolderSnapshot]


class LaunchpadAdapter(ABC):
    """One adapter per data provider (Helius, Bitquery, ...).
    A single adapter may cover multiple launchpads on the same chain
    (e.g. the Bitquery adapter covers both Four.meme and Flap on BSC)."""

    name: str = "base"
    network: str = "unknown"

    @abstractmethod
    async def connect(self) -> None:
        """Open the underlying WebSocket/gRPC/subscription connection."""
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stream_events(self) -> AsyncIterator[StreamEvent]:
        """Yield normalized events (already converted via ingestion/normalizer.py).
        Must keep running until disconnect() is called, and must handle its
        own reconnect logic on transient failures."""
        raise NotImplementedError
        yield  # pragma: no cover - makes this an async generator for type checkers

    @abstractmethod
    async def health(self) -> dict:
        """Return {'connected': bool, 'latency_ms': float | None, 'last_event_at': str | None}"""
        raise NotImplementedError
