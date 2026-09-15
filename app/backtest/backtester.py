"""
Backtesting engine skeleton.

Answers the spec's core backtest question: "when a newly launched token
had these features during the first 1s/5s/.../10m, what happened
afterwards?" — by joining feature_snapshots (what was known at time T)
against prediction_outcomes (what actually happened by T+horizon).

This file defines the metric computation; the outcome-labeling job
(deciding what counts as a "breakout" — e.g. price +N% within the
horizon — belongs in a separate scheduled task once real trade history
exists, since it needs a fixed, documented definition agreed on before
scoring anything).
"""
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.db.models import PredictionOutcomeRow, BacktestResultRow


@dataclass
class HorizonMetrics:
    horizon: str
    sample_size: int
    precision: float
    recall: float
    accuracy: float
    false_positive_rate: float
    false_negative_rate: float
    breakout_detection_rate: float
    calibration_error: float


def _confusion(rows: list[PredictionOutcomeRow], threshold: float = 0.5):
    tp = fp = tn = fn = 0
    for r in rows:
        if r.actual_breakout is None:
            continue
        predicted_positive = r.predicted_probability >= threshold
        actual_positive = bool(r.actual_breakout)
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive and not actual_positive:
            fp += 1
        elif not predicted_positive and not actual_positive:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def _calibration_error(rows: list[PredictionOutcomeRow], bins: int = 10) -> float:
    """Mean |predicted probability - observed frequency| across probability
    buckets — a simple reliability/calibration measure."""
    resolved = [r for r in rows if r.actual_breakout is not None]
    if not resolved:
        return 0.0
    total_error, total_weight = 0.0, 0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        bucket = [r for r in resolved if lo <= r.predicted_probability < hi]
        if not bucket:
            continue
        observed = sum(r.actual_breakout for r in bucket) / len(bucket)
        predicted_mean = sum(r.predicted_probability for r in bucket) / len(bucket)
        total_error += abs(predicted_mean - observed) * len(bucket)
        total_weight += len(bucket)
    return total_error / total_weight if total_weight else 0.0


def compute_horizon_metrics(db: Session, horizon: str, threshold: float = 0.5) -> HorizonMetrics:
    rows = db.query(PredictionOutcomeRow).filter(PredictionOutcomeRow.horizon == horizon).all()
    resolved = [r for r in rows if r.actual_breakout is not None]
    tp, fp, tn, fn = _confusion(resolved, threshold)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    accuracy = (tp + tn) / len(resolved) if resolved else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    breakout_rate = sum(r.actual_breakout for r in resolved) / len(resolved) if resolved else 0.0
    calibration = _calibration_error(resolved)

    return HorizonMetrics(
        horizon=horizon,
        sample_size=len(resolved),
        precision=precision,
        recall=recall,
        accuracy=accuracy,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        breakout_detection_rate=breakout_rate,
        calibration_error=calibration,
    )


def run_backtest(db: Session, horizons: list[str], threshold: float = 0.5) -> list[HorizonMetrics]:
    results = []
    for h in horizons:
        m = compute_horizon_metrics(db, h, threshold)
        db.add(BacktestResultRow(
            horizon=m.horizon, sample_size=m.sample_size, precision=m.precision,
            recall=m.recall, accuracy=m.accuracy, false_positive_rate=m.false_positive_rate,
            false_negative_rate=m.false_negative_rate, breakout_detection_rate=m.breakout_detection_rate,
            calibration_error=m.calibration_error, notes=f"threshold={threshold}",
        ))
        results.append(m)
    db.commit()
    return results
