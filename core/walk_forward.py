from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
import json
import math
import pandas as pd

from core.backtest_engine import BacktestEngine
from core.feature_builder import add_indicators
from core.backtest_report import compute_window_metrics


@dataclass(frozen=True)
class WalkForwardConfig:
    train_window_days: int = 60
    test_window_days: int = 10
    step_days: int = 10
    starting_capital: float = 100000.0
    output_dir: str = "reports/walk_forward"


def _normalize_timestamp_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts_col = None
    for candidate in ("datetime", "timestamp", "date", "ts"):
        if candidate in out.columns:
            ts_col = candidate
            break
    if ts_col is None:
        raise ValueError(
            "walk_forward requires one timestamp column in {'datetime','timestamp','date','ts'}"
        )
    out["_wf_ts"] = pd.to_datetime(out[ts_col], errors="coerce")
    if out["_wf_ts"].isna().all():
        raise ValueError("walk_forward could not parse timestamp column to datetime")
    out = out.dropna(subset=["_wf_ts"]).reset_index(drop=True)
    out["_wf_day"] = out["_wf_ts"].dt.floor("D")
    return out


def _train_stats(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    try:
        d = add_indicators(df).dropna()
        if d.empty:
            return {}
        ret_vol = d["return_1"].std()
        atr_norm = (d["atr_14"] / d["close"]).median()
        vol_target = ret_vol if ret_vol and ret_vol > 0 else atr_norm
        return {"vol_target": float(vol_target) if vol_target else None}
    except Exception:
        return {}


def _build_windows(
    df: pd.DataFrame,
    cfg: WalkForwardConfig,
) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    unique_days = sorted(df["_wf_day"].dropna().unique())
    windows: List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    total_days = len(unique_days)
    if total_days < (cfg.train_window_days + cfg.test_window_days):
        return windows

    start_idx = cfg.train_window_days
    while start_idx + cfg.test_window_days <= total_days:
        train_start = unique_days[start_idx - cfg.train_window_days]
        train_end = unique_days[start_idx - 1]
        test_start = unique_days[start_idx]
        test_end = unique_days[start_idx + cfg.test_window_days - 1]
        windows.append((train_start, train_end, test_start, test_end))
        start_idx += cfg.step_days
    return windows


def run_walk_forward(
    historical_data: pd.DataFrame,
    train_window_days: int = 60,
    test_window_days: int = 10,
    step_days: int = 10,
    starting_capital: float = 100000.0,
    output_dir: str = "reports/walk_forward",
    backtest_factory: Optional[Callable[[pd.DataFrame, float, Dict[str, Optional[float]]], object]] = None,
    write_outputs: bool = True,
) -> Dict[str, object]:
    cfg = WalkForwardConfig(
        train_window_days=train_window_days,
        test_window_days=test_window_days,
        step_days=step_days,
        starting_capital=starting_capital,
        output_dir=output_dir,
    )
    df = _normalize_timestamp_column(historical_data)
    windows = _build_windows(df, cfg)
    if not windows:
        raise ValueError(
            "Insufficient history for walk-forward windows. "
            f"Need at least {cfg.train_window_days + cfg.test_window_days} unique days."
        )

    if backtest_factory is None:
        def _factory(test_df: pd.DataFrame, capital: float, train_stats: Dict[str, Optional[float]]):
            return BacktestEngine(test_df, starting_capital=capital, train_stats=train_stats)
        backtest_factory = _factory

    window_rows: List[Dict[str, object]] = []
    all_trades: List[pd.DataFrame] = []
    for window_idx, (train_start, train_end, test_start, test_end) in enumerate(windows, start=1):
        train_df = df[(df["_wf_day"] >= train_start) & (df["_wf_day"] <= train_end)].copy()
        test_df = df[(df["_wf_day"] >= test_start) & (df["_wf_day"] <= test_end)].copy()

        # Drop helper columns before entering strategy/backtest logic.
        train_stats = _train_stats(train_df.drop(columns=["_wf_ts", "_wf_day"], errors="ignore"))
        engine = backtest_factory(
            test_df.drop(columns=["_wf_ts", "_wf_day"], errors="ignore"),
            cfg.starting_capital,
            train_stats,
        )
        if not hasattr(engine, "run"):
            raise TypeError("backtest_factory must return an object with .run()")
        results_df = engine.run()
        if results_df is None:
            results_df = pd.DataFrame()

        metrics = compute_window_metrics(results_df, starting_capital=cfg.starting_capital)
        row = {
            "window_id": window_idx,
            "train_start": str(pd.Timestamp(train_start).date()),
            "train_end": str(pd.Timestamp(train_end).date()),
            "test_start": str(pd.Timestamp(test_start).date()),
            "test_end": str(pd.Timestamp(test_end).date()),
            "return": metrics["return"],
            "max_drawdown": metrics["max_drawdown"],
            "win_rate": metrics["win_rate"],
            "avg_r": metrics["avg_r"],
            "trade_count": metrics["trade_count"],
            "sharpe_proxy": metrics["sharpe_proxy"],
        }
        window_rows.append(row)
        if not results_df.empty:
            tagged = results_df.copy()
            tagged["window_id"] = window_idx
            all_trades.append(tagged)

    window_df = pd.DataFrame(window_rows)
    trades_df = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()

    summary = {
        "config": {
            "train_window_days": cfg.train_window_days,
            "test_window_days": cfg.test_window_days,
            "step_days": cfg.step_days,
            "starting_capital": cfg.starting_capital,
            "window_count": int(len(window_df)),
        },
        "aggregate": {
            "avg_return": float(window_df["return"].mean()) if not window_df.empty else 0.0,
            "avg_max_drawdown": float(window_df["max_drawdown"].mean()) if not window_df.empty else 0.0,
            "avg_win_rate": float(window_df["win_rate"].mean()) if not window_df.empty else 0.0,
            "avg_r": float(window_df["avg_r"].mean()) if not window_df.empty else 0.0,
            "avg_sharpe_proxy": float(window_df["sharpe_proxy"].mean()) if not window_df.empty else 0.0,
            "total_trades": int(window_df["trade_count"].sum()) if not window_df.empty else 0,
        },
        "windows": window_rows,
    }

    if write_outputs:
        out_dir = Path(cfg.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_label = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        json_path = out_dir / f"walk_forward_{ts_label}.json"
        csv_path = out_dir / f"walk_forward_{ts_label}.csv"
        latest_json_path = out_dir / "walk_forward_latest.json"
        latest_csv_path = out_dir / "walk_forward_latest.csv"
        json_path.write_text(json.dumps(summary, indent=2))
        latest_json_path.write_text(json.dumps(summary, indent=2))
        window_df.to_csv(csv_path, index=False)
        window_df.to_csv(latest_csv_path, index=False)
        summary["artifacts"] = {
            "json": str(json_path),
            "csv": str(csv_path),
            "latest_json": str(latest_json_path),
            "latest_csv": str(latest_csv_path),
        }

    summary["window_df"] = window_df
    summary["trades_df"] = trades_df
    return summary


def walk_forward(historical_data: pd.DataFrame, train_size: float = 0.6, step: int = 200):
    """
    Backward-compatible walk-forward API used by existing run_backtest.
    Returns concatenated trade rows.
    """
    all_results = []
    n = len(historical_data)
    start_train = int(n * train_size)
    for start in range(start_train, n - step, step):
        train_df = historical_data.iloc[:start]
        test_df = historical_data.iloc[start:start + step]
        stats = _train_stats(train_df)
        engine = BacktestEngine(test_df, train_stats=stats)
        results = engine.run()
        all_results.append(results)
    if not all_results:
        return pd.DataFrame()
    return pd.concat(all_results, ignore_index=True)


def load_latest_walk_forward_summary(path: str = "reports/walk_forward/walk_forward_latest.json") -> tuple[dict, str | None]:
    report_path = Path(path)
    if not report_path.exists():
        return {}, "walk_forward_report_missing"
    try:
        payload = json.loads(report_path.read_text())
    except Exception as exc:
        return {}, f"walk_forward_report_invalid:{type(exc).__name__}"
    return payload, None


def promotion_metrics_from_summary(summary: dict) -> tuple[dict, str | None]:
    if not summary:
        return {}, "walk_forward_summary_empty"
    comparison = summary.get("model_comparison")
    if isinstance(comparison, dict) and comparison:
        return comparison, None
    aggregate = summary.get("aggregate")
    if isinstance(aggregate, dict) and aggregate:
        # Fallback: only one model present, use aggregate as challenger proxy.
        return {
            "challenger_return": float(aggregate.get("avg_return") or 0.0),
            "challenger_max_drawdown": float(aggregate.get("avg_max_drawdown") or 0.0),
        }, None
    return {}, "walk_forward_metrics_missing"
