"""
Converts provider-specific raw payloads into the common event schema
(ingestion/schemas.py). Each adapter calls the relevant `normalize_*`
function so the rest of the pipeline never branches on provider or chain.
"""
from datetime import datetime, timezone
from .schemas import TokenLaunchEvent, TradeEvent, LiquiditySnapshot, HolderSnapshot


def _utc(ts) -> datetime:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return ts


def normalize_helius_launch(raw: dict) -> TokenLaunchEvent:
    """raw: a pump.fun create-instruction event surfaced by Helius
    (webhook payload or enhanced-transaction event)."""
    return TokenLaunchEvent(
        token_address=raw["mint"],
        network="solana",
        launchpad="pump.fun",
        name=raw.get("name", "Unknown"),
        symbol=raw.get("symbol", "???"),
        creator_address=raw.get("creator", raw.get("user", "")),
        launch_time=_utc(raw["timestamp"]),
        initial_liquidity=float(raw.get("virtualSolReserves", 0)) / 1e9,
        provider_event_ts=_utc(raw["timestamp"]),
    )


def normalize_helius_trade(raw: dict) -> TradeEvent:
    return TradeEvent(
        token_address=raw["mint"],
        network="solana",
        side="buy" if raw.get("isBuy") else "sell",
        wallet_address=raw.get("user", ""),
        amount_base=float(raw.get("tokenAmount", 0)),
        amount_quote=float(raw.get("solAmount", 0)) / 1e9,
        price=float(raw.get("price", 0)),
        tx_hash=raw.get("signature", ""),
        provider_event_ts=_utc(raw["timestamp"]),
    )


def normalize_bitquery_launch(raw: dict) -> TokenLaunchEvent:
    """raw: a Four.meme / Flap token-creation event from a Bitquery
    GraphQL subscription (EVM DEXTrades / TokenSupplyUpdates)."""
    launchpad = "four.meme" if raw.get("factory", "").lower().find("four") >= 0 else "flap"
    return TokenLaunchEvent(
        token_address=raw["tokenAddress"],
        network="bsc",
        launchpad=launchpad,
        name=raw.get("name", "Unknown"),
        symbol=raw.get("symbol", "???"),
        creator_address=raw.get("creatorAddress", ""),
        launch_time=_utc(raw["block"]["timestamp"]),
        initial_liquidity=float(raw.get("initialLiquidity", 0)),
        provider_event_ts=_utc(raw["block"]["timestamp"]),
    )


def normalize_bitquery_trade(raw: dict) -> TradeEvent:
    return TradeEvent(
        token_address=raw["tokenAddress"],
        network="bsc",
        side=raw.get("side", "buy"),
        wallet_address=raw.get("trader", ""),
        amount_base=float(raw.get("baseAmount", 0)),
        amount_quote=float(raw.get("quoteAmount", 0)),
        price=float(raw.get("price", 0)),
        tx_hash=raw.get("transactionHash", ""),
        provider_event_ts=_utc(raw["block"]["timestamp"]),
    )
