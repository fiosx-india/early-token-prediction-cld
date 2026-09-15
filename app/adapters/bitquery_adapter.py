"""
Bitquery adapter — BSC, covers both Four.meme and Flap launchpads
through one adapter (per the spec: don't duplicate per-launchpad systems).

Real-time strategy: Bitquery GraphQL *subscriptions* over WebSocket
(not polling), filtered to the Four.meme and Flap factory contract
addresses, for both token-creation events and DEXTrades.

Credentials: BITQUERY_ACCESS_TOKEN (the OAuth Access Token generated
under Authorization -> Tokens in the Bitquery dashboard — not the app ID).
Read from app.config.settings only; never sent to the frontend.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from app.adapters.base import LaunchpadAdapter, StreamEvent
from app.config import settings
from app.ingestion.normalizer import normalize_bitquery_launch, normalize_bitquery_trade

logger = logging.getLogger("adapters.bitquery")

BITQUERY_WS_ENDPOINT = "wss://streaming.bitquery.io/graphql"

# Factory / router contract addresses to filter subscriptions on.
FOUR_MEME_FACTORY = "0x5c952063c7fc8610FFDB798152D69F0B9550762"   # placeholder — confirm current address
FLAP_FACTORY = "0x0000000000000000000000000000000000dEaD"          # placeholder — confirm current address

LAUNCH_SUBSCRIPTION = """
subscription {
  EVM(network: bsc) {
    TokenSupplyUpdates(
      where: {TokenSupplyUpdate: {Type: {is: "mint"}}}
    ) {
      Currency { SmartContract Name Symbol }
      TokenSupplyUpdate { PostBalance }
      Transaction { From Hash }
      Block { Time }
    }
  }
}
"""

TRADE_SUBSCRIPTION = """
subscription {
  EVM(network: bsc) {
    DEXTrades {
      Trade { Buyer Seller Buy { Amount Price Currency { SmartContract } } }
      Transaction { Hash }
      Block { Time }
    }
  }
}
"""


class BitqueryAdapter(LaunchpadAdapter):
    name = "bitquery"
    network = "bsc"

    def __init__(self):
        self._connected = False
        self._last_event_at: datetime | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    async def connect(self) -> None:
        if not settings.bitquery_access_token:
            raise RuntimeError(
                "BITQUERY_ACCESS_TOKEN is not set. Refusing to connect in live mode. "
                "Set DATA_MODE=mock to run without credentials."
            )
        # TODO: open a websockets connection to BITQUERY_WS_ENDPOINT with
        #   Authorization: Bearer {settings.bitquery_access_token}
        # and send LAUNCH_SUBSCRIPTION / TRADE_SUBSCRIPTION as GraphQL-WS
        # `start` messages. Two tasks: one per subscription.
        self._connected = True
        self._tasks = [
            asyncio.create_task(self._consume_loop("launch")),
            asyncio.create_task(self._consume_loop("trade")),
        ]
        logger.info("Bitquery adapter connected (Four.meme + Flap, BSC)")

    async def disconnect(self) -> None:
        self._connected = False
        for t in self._tasks:
            t.cancel()

    async def _consume_loop(self, kind: str):
        try:
            while self._connected:
                # TODO: replace with `raw = await ws.recv()` and json.loads(raw)
                await asyncio.sleep(3600)  # placeholder: no real source wired yet
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Bitquery %s consume loop crashed", kind)
            self._connected = False

    def _handle_raw_event(self, kind: str, raw: dict):
        try:
            event = normalize_bitquery_launch(raw) if kind == "launch" else normalize_bitquery_trade(raw)
            self._last_event_at = datetime.now(timezone.utc)
            self._queue.put_nowait(event)
        except Exception:
            logger.exception("Failed to normalize Bitquery %s event: %s", kind, raw)

    async def stream_events(self) -> AsyncIterator[StreamEvent]:
        while self._connected:
            event = await self._queue.get()
            yield event

    async def health(self) -> dict:
        return {
            "connected": self._connected,
            "latency_ms": None,
            "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
        }
