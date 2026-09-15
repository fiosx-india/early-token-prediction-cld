"""
Application entrypoint. Wires together:
  adapter (mock or live) -> normalizer (done inside adapters) ->
  feature engine -> risk engine -> prediction engine -> DB + WebSocket

Run with:  uvicorn app.main:app --reload --port 8000
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db, SessionLocal
from app.db.models import Token, Trade, PredictionResultRow, RiskIndicatorRow
from app.ingestion.schemas import TokenLaunchEvent, TradeEvent
from app.features.feature_engine import FeatureEngine
from app.risk.risk_engine import assess as assess_risk
from app.prediction.prediction_engine import predict
from app.api.routes import router as api_router
from app.api.websocket import manager

from app.adapters.mock_adapter import MockAdapter
from app.adapters.helius_adapter import HeliusAdapter
from app.adapters.bitquery_adapter import BitqueryAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="Early Token Prediction")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router, prefix="/api")

feature_engine = FeatureEngine(window_seconds=settings.feature_window_seconds)


def build_adapters() -> list:
    """Mock mode -> one MockAdapter covering everything.
    Live mode -> Helius (Solana) + Bitquery (BSC) side by side, each
    only started if its credential is actually present."""
    if settings.data_mode != "live":
        return [MockAdapter()]

    adapters = []
    if settings.helius_api_key:
        adapters.append(HeliusAdapter())
    else:
        logger.warning("HELIUS_API_KEY missing — Solana/pump.fun stream disabled")
    if settings.bitquery_access_token:
        adapters.append(BitqueryAdapter())
    else:
        logger.warning("BITQUERY_ACCESS_TOKEN missing — BSC stream disabled")
    if not adapters:
        logger.warning("No live credentials configured — falling back to MockAdapter")
        adapters.append(MockAdapter())
    return adapters


async def handle_event(event, db_session_factory):
    now = datetime.now(timezone.utc)

    if isinstance(event, TokenLaunchEvent):
        feature_engine.register_launch(event)
        db = db_session_factory()
        try:
            db.merge(Token(
                token_address=event.token_address, network=event.network,
                launchpad=event.launchpad, name=event.name, symbol=event.symbol,
                creator_address=event.creator_address, launch_time=event.launch_time,
                initial_liquidity=event.initial_liquidity,
            ))
            db.commit()
        finally:
            db.close()
        await manager.broadcast({"type": "launch", "token_address": event.token_address,
                                  "network": event.network, "launchpad": event.launchpad,
                                  "name": event.name, "symbol": event.symbol})
        return

    if isinstance(event, TradeEvent):
        feature_engine.ingest_trade(event)
        db = db_session_factory()
        try:
            db.add(Trade(
                token_address=event.token_address, network=event.network, side=event.side,
                wallet_address=event.wallet_address, amount_base=event.amount_base,
                amount_quote=event.amount_quote, price=event.price, tx_hash=event.tx_hash,
                provider_event_ts=event.provider_event_ts,
            ))
            db.commit()
        finally:
            db.close()

        feature = feature_engine.compute(event.token_address, now)
        if feature is None:
            return
        risk = assess_risk(feature)
        result = predict(feature, risk)
        if result is None:
            return

        db = db_session_factory()
        try:
            db.add(RiskIndicatorRow(
                token_address=event.token_address, captured_at=now,
                concentration_score=risk.concentration_score, wash_trading_score=risk.wash_trading_score,
                creator_risk_score=risk.creator_risk_score, liquidity_risk_score=risk.liquidity_risk_score,
                overall_risk_level=risk.overall_risk_level, flags=json.dumps(risk.flags),
            ))
            for horizon, hp in result.horizons.items():
                db.add(PredictionResultRow(
                    token_address=event.token_address, horizon=horizon, probability=hp.probability,
                    confidence=hp.confidence, risk_level=risk.overall_risk_level, computed_at=now,
                    supporting_evidence=json.dumps(result.supporting_evidence),
                    conflicting_evidence=json.dumps(result.conflicting_evidence),
                ))
            db.commit()
        finally:
            db.close()

        await manager.broadcast({
            "type": "prediction",
            "token_address": event.token_address,
            "risk_level": risk.overall_risk_level,
            "horizons": {h: hp.probability for h, hp in result.horizons.items()},
            "supporting_evidence": result.supporting_evidence,
            "conflicting_evidence": result.conflicting_evidence,
            "computed_at": now.isoformat(),
            # raw feature snapshot, so the dashboard can show live numbers
            # (buys/sec, buyers, liquidity, etc.) without a separate call
            "features": {
                "age_seconds": feature.age_seconds,
                "buys_per_second": feature.buys_per_second,
                "txs_per_second": feature.txs_per_second,
                "unique_buyers_total": feature.unique_buyers_total,
                "buy_volume": feature.buy_volume,
                "price_velocity": feature.price_velocity,
                "liquidity": feature.liquidity,
                "holder_growth": feature.holder_growth,
                "top_holder_share": risk.concentration_score,
            },
        })


async def run_adapter(adapter):
    await adapter.connect()
    try:
        async for event in adapter.stream_events():
            await handle_event(event, SessionLocal)
    finally:
        await adapter.disconnect()


@app.on_event("startup")
async def startup():
    init_db()
    adapters = build_adapters()
    for adapter in adapters:
        asyncio.create_task(run_adapter(adapter))
    logger.info("Started %d adapter(s) in %s mode", len(adapters), settings.data_mode)


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # dashboard doesn't need to send anything; keeps conn alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
