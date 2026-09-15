"""
Mock adapter — generates simulated launches + trades so the entire
pipeline (features -> prediction -> risk -> API -> dashboard) runs
end-to-end with zero credentials. Used whenever DATA_MODE=mock, and
automatically whenever a live adapter's API key is missing.

This is the ONLY adapter allowed to invent data. Every other adapter
must fail loudly (see helius_adapter/bitquery_adapter connect()) rather
than silently substitute fake numbers — the spec's "do not fabricate
blockchain data" rule applies to the live path.
"""
import asyncio
import random
import string
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from app.adapters.base import LaunchpadAdapter, StreamEvent
from app.ingestion.schemas import TokenLaunchEvent, TradeEvent

NETWORKS = [
    ("solana", "pump.fun"),
    ("bsc", "four.meme"),
    ("bsc", "flap"),
]
NAME_PARTS1 = ["Doge", "Pepe", "Moon", "Chad", "Wojak", "Frog", "Turbo", "Based", "Ninja", "Rocket"]
NAME_PARTS2 = ["King", "Coin", "Inu", "X", "Finance", "Verse", "AI", "Prime", "Wave", "Nova"]


def _rand_addr(n=8) -> str:
    return "0x" + "".join(random.choices(string.hexdigits.lower(), k=n))


class MockAdapter(LaunchpadAdapter):
    name = "mock"
    network = "mixed"

    def __init__(self):
        self._connected = False
        self._known_tokens: list[str] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def stream_events(self) -> AsyncIterator[StreamEvent]:
        while self._connected:
            await asyncio.sleep(random.uniform(0.5, 2.0))
            now = datetime.now(timezone.utc)

            # occasionally launch a brand-new token
            if not self._known_tokens or random.random() < 0.15:
                network, launchpad = random.choice(NETWORKS)
                addr = _rand_addr(12)
                self._known_tokens.append(addr)
                if len(self._known_tokens) > 80:
                    self._known_tokens.pop(0)
                yield TokenLaunchEvent(
                    token_address=addr,
                    network=network,
                    launchpad=launchpad,
                    name=random.choice(NAME_PARTS1) + random.choice(NAME_PARTS2),
                    symbol=random.choice(NAME_PARTS1)[:4].upper(),
                    creator_address=_rand_addr(),
                    launch_time=now,
                    initial_liquidity=random.uniform(500, 15000),
                    provider_event_ts=now,
                )
                continue

            # otherwise, emit a trade against a known token
            addr = random.choice(self._known_tokens)
            network = "solana" if addr in self._known_tokens[::2] else "bsc"
            yield TradeEvent(
                token_address=addr,
                network=network,
                side="buy" if random.random() < 0.7 else "sell",
                wallet_address=_rand_addr(),
                amount_base=random.uniform(100, 50000),
                amount_quote=random.uniform(0.01, 5),
                price=random.uniform(0.0000001, 0.01),
                tx_hash=uuid.uuid4().hex,
                provider_event_ts=now,
            )

    async def health(self) -> dict:
        return {"connected": self._connected, "latency_ms": random.uniform(20, 80), "last_event_at": datetime.now(timezone.utc).isoformat()}
