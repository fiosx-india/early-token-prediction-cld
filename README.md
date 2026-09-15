# Early Token Prediction — Backend (Phase 2)

Real-time meme-token breakout detection & prediction backend for Solana
(pump.fun via Helius) and BSC (Four.meme, Flap via Bitquery).

This is **not** a trading bot. It only detects, scores, and surfaces
probabilities. No order execution exists anywhere in this codebase.

## Architecture (matches the original spec's 11 layers)

```
                 ┌────────────────────────────────────────────┐
                 │              Provider Adapters              │
                 │  helius_adapter.py   bitquery_adapter.py    │
                 │  (implements LaunchpadAdapter interface)     │
                 └───────────────┬──────────────────────────────┘
                                 │ raw provider events (stream)
                                 ▼
                 ┌────────────────────────────────────────────┐
                 │        Launchpad Detection (per adapter)     │
                 │  pump.fun create-event / Four.meme / Flap    │
                 └───────────────┬──────────────────────────────┘
                                 │ raw launch/trade events
                                 ▼
                 ┌────────────────────────────────────────────┐
                 │   Normalization (ingestion/normalizer.py)    │
                 │   -> common TokenEvent / TradeEvent schema   │
                 └───────────────┬──────────────────────────────┘
                                 │ normalized events
                                 ▼
                 ┌────────────────────────────────────────────┐
                 │   Feature Engine (features/feature_engine)   │
                 │   buys/sec, accel, holder growth, wallet Q   │
                 └───────────────┬──────────────────────────────┘
                                 │ feature snapshot (per token, per tick)
                                 ▼
                 ┌───────────────────────┬──────────────────────┐
                 │  Prediction Engine     │   Risk Engine         │
                 │  13 horizons, weighted │   concentration,      │
                 │  per horizon           │   wash-trading flags  │
                 └───────────┬───────────┴──────────┬───────────┘
                             │                       │
                             ▼                       ▼
                 ┌────────────────────────────────────────────┐
                 │         Storage (SQLite/Postgres via         │
                 │         SQLAlchemy — db/models.py)           │
                 │  tokens, trades, feature_snapshots,          │
                 │  predictions, prediction_outcomes,           │
                 │  creator_history, risk_indicators            │
                 └───────────────┬──────────────────────────────┘
                                 │
                 ┌───────────────┴──────────────────────────────┐
                 │        API Layer (FastAPI) — api/routes.py    │
                 │        REST for history + WebSocket for live  │
                 └───────────────┬──────────────────────────────┘
                                 │
                                 ▼
                     Dashboard (the HTML artifact / any frontend)
```

## Data flow, in one sentence per hop

1. Adapter opens a WebSocket/gRPC stream to Helius or Bitquery and yields raw events.
2. The adapter's own `detect_launch()` recognizes a pump.fun / Four.meme / Flap
   creation event and emits a `TokenEvent`.
3. `normalizer.py` converts provider-specific payloads into one common shape
   (`TokenEvent`, `TradeEvent`) so nothing downstream cares which chain it came from.
4. `feature_engine.py` keeps a rolling per-token state (ring buffer of recent
   trades) and computes the feature set on every new event or on a fixed tick.
5. `prediction_engine.py` takes the feature snapshot and produces one
   probability per horizon (1s → 24h), using a **different weight profile per
   horizon** (short horizons lean on momentum/buyers, long horizons lean on
   sustain/liquidity/creator history).
6. `risk_engine.py` runs independently and produces concentration / wash-trading
   / creator-risk flags that both feed the prediction (as a feature) and are
   shown standalone in the evidence panel.
7. Every snapshot + prediction is persisted so `backtest/backtester.py` can
   later replay "what happened after tokens with these first-N-second
   features" once outcomes are recorded.
8. `api/routes.py` exposes REST endpoints for history/backtest and a
   WebSocket endpoint that pushes new snapshots to any connected dashboard.

## Why not Streamlit Cloud for this part

Your other projects (nifty-market-intelligence, binance-futures-scanner) run
well on Streamlit Cloud because they poll on a schedule. This backend needs a
**long-lived process holding open WebSocket/gRPC connections 24/7** — Streamlit
Cloud sleeps/restarts apps and doesn't support persistent background workers.
For this service, use a host built for long-running processes:
Railway, Render, Fly.io, or a small VPS. The dashboard (frontend) can still be
anything, including a Streamlit page that connects to this backend's WebSocket.

## Running locally (once you have a machine with network access)

```bash
cp .env.example .env          # fill in HELIUS_API_KEY / BITQUERY_ACCESS_TOKEN
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

With no keys set, `DATA_MODE=mock` (the default) runs the mock adapter so the
API/WebSocket/dashboard all work end-to-end with simulated data — same demo
mode as the HTML dashboard from Phase 1.

## Folder map

| Path | Responsibility |
|---|---|
| `app/adapters/` | One file per provider, all implementing `LaunchpadAdapter` |
| `app/ingestion/` | Launch detection + normalization into common event schema |
| `app/features/` | Rolling feature computation per token |
| `app/prediction/` | Horizon definitions + weighted scoring |
| `app/risk/` | Concentration / wash-trading / creator-risk scoring |
| `app/db/` | SQLAlchemy models + schema + session handling |
| `app/api/` | FastAPI REST routes + WebSocket broadcast |
| `app/backtest/` | Historical replay + precision/recall/calibration metrics |
