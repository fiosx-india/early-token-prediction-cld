"""
SQLAlchemy models covering every table the spec's DATABASE section
calls for. Designed for high-frequency time-series writes: snapshot
tables use (token_address, captured_at) as their natural key and are
meant to be append-only — never updated in place — so backtesting can
replay exactly what was known at each point in time.
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Token(Base):
    __tablename__ = "tokens"
    token_address = Column(String, primary_key=True)
    network = Column(String, nullable=False)
    launchpad = Column(String, nullable=False)
    name = Column(String)
    symbol = Column(String)
    creator_address = Column(String, index=True)
    launch_time = Column(DateTime, nullable=False)
    initial_liquidity = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("tokens.token_address"), index=True)
    network = Column(String, nullable=False)
    side = Column(String, nullable=False)
    wallet_address = Column(String, index=True)
    amount_base = Column(Float)
    amount_quote = Column(Float)
    price = Column(Float)
    tx_hash = Column(String, unique=True)
    provider_event_ts = Column(DateTime, nullable=False, index=True)
    ingested_at = Column(DateTime, default=datetime.utcnow)


Index("ix_trades_token_time", Trade.token_address, Trade.provider_event_ts)


class LiquiditySnapshotRow(Base):
    __tablename__ = "liquidity_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("tokens.token_address"), index=True)
    liquidity_quote = Column(Float)
    captured_at = Column(DateTime, nullable=False, index=True)


class HolderSnapshotRow(Base):
    __tablename__ = "holder_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("tokens.token_address"), index=True)
    holder_count = Column(Integer)
    top_holder_share = Column(Float, nullable=True)
    captured_at = Column(DateTime, nullable=False, index=True)


class FeatureSnapshotRow(Base):
    __tablename__ = "feature_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("tokens.token_address"), index=True)
    captured_at = Column(DateTime, nullable=False, index=True)
    age_seconds = Column(Float)
    buys_per_second = Column(Float)
    txs_per_second = Column(Float)
    unique_buyers_per_second = Column(Float)
    buy_volume = Column(Float)
    buy_volume_accel = Column(Float)
    tx_accel = Column(Float)
    price_velocity = Column(Float)
    price_accel = Column(Float)
    liquidity = Column(Float)
    liquidity_change = Column(Float)
    holder_growth = Column(Float)
    holder_growth_accel = Column(Float)
    market_activity_accel = Column(Float)
    top_holder_share = Column(Float, nullable=True)


class PredictionResultRow(Base):
    __tablename__ = "prediction_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("tokens.token_address"), index=True)
    horizon = Column(String, nullable=False)  # "1s".."24h"
    probability = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    risk_level = Column(String)
    computed_at = Column(DateTime, nullable=False, index=True)
    supporting_evidence = Column(Text)   # JSON-encoded list
    conflicting_evidence = Column(Text)  # JSON-encoded list


Index("ix_predictions_token_horizon_time", PredictionResultRow.token_address,
      PredictionResultRow.horizon, PredictionResultRow.computed_at)


class PredictionOutcomeRow(Base):
    """Filled in later by the backtester: what actually happened after
    a given prediction, so precision/recall/calibration can be measured."""
    __tablename__ = "prediction_outcomes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("tokens.token_address"), index=True)
    horizon = Column(String, nullable=False)
    predicted_probability = Column(Float, nullable=False)
    actual_breakout = Column(Integer, nullable=True)  # 1/0, null until resolved
    actual_price_change_pct = Column(Float, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    evaluated_at = Column(DateTime, default=datetime.utcnow)


class CreatorHistoryRow(Base):
    __tablename__ = "creator_history"
    creator_address = Column(String, primary_key=True)
    tokens_created = Column(Integer, default=0)
    tokens_rugged_estimate = Column(Integer, default=0)
    history_score = Column(Float, default=0.5)  # 0=risky .. 1=clean
    last_updated = Column(DateTime, default=datetime.utcnow)


class RiskIndicatorRow(Base):
    __tablename__ = "risk_indicators"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_address = Column(String, ForeignKey("tokens.token_address"), index=True)
    captured_at = Column(DateTime, nullable=False, index=True)
    concentration_score = Column(Float)
    wash_trading_score = Column(Float)
    creator_risk_score = Column(Float)
    liquidity_risk_score = Column(Float)
    overall_risk_level = Column(String)
    flags = Column(Text)  # JSON-encoded list


class BacktestResultRow(Base):
    __tablename__ = "backtest_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime, default=datetime.utcnow)
    horizon = Column(String, nullable=False)
    sample_size = Column(Integer)
    precision = Column(Float)
    recall = Column(Float)
    accuracy = Column(Float)
    false_positive_rate = Column(Float)
    false_negative_rate = Column(Float)
    breakout_detection_rate = Column(Float)
    calibration_error = Column(Float)
    notes = Column(Text)
