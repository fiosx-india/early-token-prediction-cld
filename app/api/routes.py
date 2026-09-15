"""
REST endpoints: health/status, token list, token detail + prediction,
and a manual backtest trigger. Real-time delivery is via the WebSocket
endpoint registered in main.py (kept separate from routes.py since it
needs the shared ConnectionManager instance).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import credentials_ready
from app.db.database import get_session
from app.db.models import Token, PredictionResultRow
from app.backtest.backtester import run_backtest
from app.prediction.horizons import HORIZON_WEIGHTS

router = APIRouter()


@router.get("/health")
def health():
    """Overall service + provider credential status (never returns the
    credential values themselves — see app/config.py)."""
    return {"status": "ok", "providers": credentials_ready()}


@router.get("/tokens")
def list_tokens(db: Session = Depends(get_session), limit: int = 50):
    rows = db.query(Token).order_by(Token.launch_time.desc()).limit(limit).all()
    return [
        {
            "token_address": r.token_address,
            "network": r.network,
            "launchpad": r.launchpad,
            "name": r.name,
            "symbol": r.symbol,
            "launch_time": r.launch_time,
        }
        for r in rows
    ]


@router.get("/tokens/{token_address}/predictions")
def token_predictions(token_address: str, db: Session = Depends(get_session)):
    rows = (
        db.query(PredictionResultRow)
        .filter(PredictionResultRow.token_address == token_address)
        .order_by(PredictionResultRow.computed_at.desc())
        .limit(len(HORIZON_WEIGHTS))
        .all()
    )
    return [
        {
            "horizon": r.horizon,
            "probability": r.probability,
            "confidence": r.confidence,
            "risk_level": r.risk_level,
            "computed_at": r.computed_at,
        }
        for r in rows
    ]


@router.post("/backtest/run")
def trigger_backtest(threshold: float = 0.5, db: Session = Depends(get_session)):
    metrics = run_backtest(db, horizons=list(HORIZON_WEIGHTS.keys()), threshold=threshold)
    return [m.__dict__ for m in metrics]
