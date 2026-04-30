from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .exporter import build_option_backtest_frame


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _load_review_queue(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("review_queue_not_list")
    return [row for row in payload if isinstance(row, dict)]


def _row_snapshot_ts_epoch(row: dict[str, Any]) -> float | None:
    for key in ("snapshot_ts_epoch", "quote_ts_epoch", "ts_epoch", "decision_ts_epoch"):
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _row_outcome_bucket(row: dict[str, Any]) -> str:
    final_action = str(row.get("final_action") or "").strip().upper()
    execution_status = str(row.get("execution_status") or "").strip().lower()
    permission = str(row.get("permission") or "").strip().upper()
    if final_action == "EXECUTE" or permission == "EXECUTE" or execution_status == "executable":
        return "execute_intent"
    return "blocked"


def _simulate_from_snapshot(
    *,
    bars: pd.DataFrame,
    snapshot_ts_epoch: float,
    side: str,
    target: float,
    stop: float,
) -> dict[str, Any]:
    if bars.empty:
        return {"outcome": "no_data"}
    bars = bars.copy()
    bars["ts_epoch"] = pd.to_datetime(bars["timestamp"]).dt.tz_localize("Asia/Kolkata").astype("int64") / 1e9
    live = bars.loc[bars["ts_epoch"] >= float(snapshot_ts_epoch)].copy()
    if live.empty:
        return {"outcome": "no_future_bars"}
    is_sell = str(side or "").upper().startswith("SELL")
    for _, bar in live.iterrows():
        high = _safe_float(bar.get("high"))
        low = _safe_float(bar.get("low"))
        if high is None or low is None:
            continue
        if is_sell:
            if low <= target:
                return {"outcome": "target_hit", "timestamp": bar["timestamp"], "price": target}
            if high >= stop:
                return {"outcome": "stop_hit", "timestamp": bar["timestamp"], "price": stop}
        else:
            if high >= target:
                return {"outcome": "target_hit", "timestamp": bar["timestamp"], "price": target}
            if low <= stop:
                return {"outcome": "stop_hit", "timestamp": bar["timestamp"], "price": stop}
    last = live.iloc[-1]
    return {"outcome": "open", "timestamp": last["timestamp"], "price": _safe_float(last.get("close"))}


def evaluate_review_queue_snapshot(
    *,
    review_queue_path: Path,
    db_path: Path,
    symbol_prefix: str | None = None,
) -> dict[str, Any]:
    rows = _load_review_queue(review_queue_path)
    evaluated: list[dict[str, Any]] = []
    bars_cache: dict[tuple[int, str], pd.DataFrame] = {}

    for row in rows:
        tradingsymbol = str(row.get("tradingsymbol") or "").strip().upper()
        if not tradingsymbol:
            continue
        if symbol_prefix and not tradingsymbol.startswith(str(symbol_prefix).upper()):
            continue
        instrument_token = row.get("instrument_token")
        try:
            token = int(instrument_token)
        except Exception:
            continue
        snapshot_ts_epoch = _row_snapshot_ts_epoch(row)
        target = _safe_float(row.get("target") if row.get("target") is not None else row.get("target_price"))
        stop = _safe_float(row.get("stop_loss") if row.get("stop_loss") is not None else row.get("stop"))
        if snapshot_ts_epoch is None or target is None or stop is None:
            continue
        trade_date = pd.to_datetime(snapshot_ts_epoch, unit="s", utc=True).tz_convert("Asia/Kolkata").date().isoformat()
        cache_key = (token, trade_date)
        if cache_key not in bars_cache:
            try:
                bars_cache[cache_key] = build_option_backtest_frame(
                    db_path=db_path,
                    instrument_token=token,
                    tradingsymbol=tradingsymbol,
                    start_ts_epoch=pd.Timestamp(trade_date, tz="Asia/Kolkata").timestamp(),
                    end_ts_epoch=(pd.Timestamp(trade_date, tz="Asia/Kolkata") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)).timestamp(),
                )
            except ValueError:
                bars_cache[cache_key] = pd.DataFrame(
                    columns=["timestamp", "symbol", "open", "high", "low", "close", "volume", "oi", "bid", "ask"]
                )
        outcome = _simulate_from_snapshot(
            bars=bars_cache[cache_key],
            snapshot_ts_epoch=snapshot_ts_epoch,
            side=str(row.get("side") or "BUY"),
            target=target,
            stop=stop,
        )
        evaluated.append(
            {
                "tradingsymbol": tradingsymbol,
                "bucket": _row_outcome_bucket(row),
                "final_action": row.get("final_action"),
                "execution_status": row.get("execution_status"),
                "status": row.get("status"),
                "entry": _safe_float(row.get("entry")),
                "target": target,
                "stop": stop,
                "snapshot_ts_ist": pd.to_datetime(snapshot_ts_epoch, unit="s", utc=True).tz_convert("Asia/Kolkata").isoformat(),
                "outcome": outcome.get("outcome"),
                "outcome_ts": outcome.get("timestamp"),
                "outcome_price": outcome.get("price"),
                "confidence": _safe_float(row.get("confidence_final") if row.get("confidence_final") is not None else row.get("confidence")),
                "primary_blocker": row.get("primary_blocker"),
            }
        )

    df = pd.DataFrame(evaluated)
    if df.empty:
        return {"rows": 0, "summary": {}, "evaluated": []}
    summary: dict[str, Any] = {}
    for bucket, sub in df.groupby("bucket"):
        summary[bucket] = {
            "rows": int(len(sub)),
            "target_hit": int((sub["outcome"] == "target_hit").sum()),
            "stop_hit": int((sub["outcome"] == "stop_hit").sum()),
            "open": int((sub["outcome"] == "open").sum()),
            "no_data": int((sub["outcome"] == "no_data").sum() + (sub["outcome"] == "no_future_bars").sum()),
        }
    return {
        "rows": int(len(df)),
        "summary": summary,
        "evaluated": df.sort_values(["bucket", "tradingsymbol"]).to_dict(orient="records"),
    }
