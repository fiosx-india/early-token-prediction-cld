"""
Helius adapter — Solana, pump.fun launch detection.

Real-time strategy (in priority order):
  1. Helius LaserStream (gRPC) subscribed to the pump.fun program ID,
     filtered to "create" and "buy/sell" instructions. This is the
     lowest-latency option and matches the spec's "avoid polling" rule.
  2. Fallback: Helius enhanced Webhooks configured against the pump.fun
     program, received on a small internal HTTP endpoint and pushed
     into the same async queue `stream_events()` reads from.

Credentials: HELIUS_API_KEY, read from app.config.settings — never
hard-coded, never sent to the frontend.

NOTE: This file defines the real connection *structure* (method shapes,
where the gRPC/webhook payload would be parsed and normalized). The
actual gRPC client wiring is left as TODOs because it depends on the
Helius LaserStream SDK version and your API tier — plug it in when you
have network access and a confirmed LaserStream plan.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from app.adapters.base import LaunchpadAdapter, StreamEvent
from app.config import settings
from app.ingestion.normalizer import normalize_helius_launch, normalize_helius_trade

logger = logging.getLogger("adapters.helius")

PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


class HeliusAdapter(LaunchpadAdapter):
    name = "helius"
    network = "solana"

    def __init__(self):
        self._connected = False
        self._last_event_at: datetime | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def connect(self) -> None:
        if not settings.helius_api_key:
            raise RuntimeError(
                "HELIUS_API_KEY is not set. Refusing to connect in live mode. "
                "Set DATA_MODE=mock to run without credentials."
            )
        # TODO: open LaserStream gRPC connection here, e.g.:
        #   channel = grpc.aio.secure_channel(LASERSTREAM_ENDPOINT, creds)
        #   stub = laserstream_pb2_grpc.LaserstreamStub(channel)
        #   request = build_subscribe_request(program_id=PUMP_FUN_PROGRAM_ID)
        #   self._stream = stub.Subscribe(request, metadata=[("x-api-key", settings.helius_api_key)])
        self._connected = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("Helius adapter connected (pump.fun, program=%s)", PUMP_FUN_PROGRAM_ID)

    async def disconnect(self) -> None:
        self._connected = False
        if self._task:
            self._task.cancel()

    async def _consume_loop(self):
        """Reads raw messages off the LaserStream/webhook source, normalizes
        them, and pushes onto the internal queue that stream_events() drains."""
        try:
            while self._connected:
                # TODO: replace with `raw = await self._stream.__anext__()`
                await asyncio.sleep(3600)  # placeholder: no real source wired yet
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Helius consume loop crashed — will need reconnect logic")
            self._connected = False

    def _handle_raw_event(self, raw: dict):
        try:
            if raw.get("type") == "create":
                event = normalize_helius_launch(raw)
            else:
                event = normalize_helius_trade(raw)
            self._last_event_at = datetime.now(timezone.utc)
            self._queue.put_nowait(event)
        except Exception:
            logger.exception("Failed to normalize Helius event: %s", raw)

    async def stream_events(self) -> AsyncIterator[StreamEvent]:
        while self._connected:
            event = await self._queue.get()
            yield event

    async def health(self) -> dict:
        return {
            "connected": self._connected,
            "latency_ms": None,  # TODO: measure round-trip on a periodic ping
            "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
        }
