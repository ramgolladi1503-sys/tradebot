from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION
from .dataset import validate_candidate_dataset


REPLAY_LEDGER_LANE = "HISTORICAL_REPLAY_LEDGER_PROXY_SELECTOR"
REPLAY_LEDGER_REQUIRED_FEATURES = (
    "direction_long",
    "symbol_nifty",
    "symbol_banknifty",
    "setup_failed_breakdown_long",
    "htf_bullish",
    "rejection_quality",
    "cost_hurdle_margin_r",
    "planned_reward_r",
    "entry_gap_r",
    "failed_level_distance_r",
    "wick_ratio",
    "minutes_since_open",
    "time_sin",
    "time_cos",
)


def _stream_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl_records(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"replay_ledger_missing:{source}")
    records: list[dict[str, Any]] = []
    rejected_lines: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            rejected_lines.append({"line_number": line_number, "reason": f"invalid_json:{exc.msg}"})
            continue
        if not isinstance(payload, dict):
            rejected_lines.append({"line_number": line_number, "reason": "jsonl_row_not_object"})
            continue
        records.append(payload)
    if not records:
        raise ValueError("replay_ledger_no_records")
    manifest = {
        "lane": REPLAY_LEDGER_LANE,
        "schema_version": SCHEMA_VERSION,
        "path": str(source),
        "sha256": _stream_sha256(source),
        "bytes": int(source.stat().st_size),
        "records": int(len(records)),
        "rejected_lines": rejected_lines,
        "rejected_line_count": int(len(rejected_lines)),
        **SAFETY_CONTRACT,
    }
    return records, manifest


def _number(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
        return value if math.isfinite(value) else float(default)
    except Exception:
        return float(default)


def _timestamp(value: Any, *, field: str) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        raise ValueError(f"replay_ledger_timestamp_invalid:{field}")
    return pd.Timestamp(timestamp)


def _risk_distance(row: Mapping[str, Any]) -> float:
    entry = _number(row, "entry_price", _number(row, "entry_open"))
    stop = _number(row, "stop_loss")
    risk = abs(entry - stop)
    if risk <= 1e-12:
        raise ValueError("replay_ledger_zero_risk")
    return risk


def _row_to_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    signal_ts = _timestamp(row.get("signal_time"), field="signal_time")
    entry_ts = _timestamp(row.get("entry_time"), field="entry_time")
    exit_ts = _timestamp(row.get("exit_time"), field="exit_time")
    if entry_ts < signal_ts:
        raise ValueError("replay_ledger_entry_before_signal")
    if exit_ts <= entry_ts:
        raise ValueError("replay_ledger_exit_not_after_entry")

    strategy_id = str(row.get("strategy_id") or "UNKNOWN").strip().upper()
    symbol = str(row.get("symbol") or "UNKNOWN").strip().upper()
    direction = str(row.get("direction") or "").strip().upper()
    setup_type = str(row.get("setup_type") or "").strip().upper()
    htf_regime = str(row.get("htf_regime") or "").strip().upper()
    exit_reason = str(row.get("exit_reason") or "").strip().upper()
    candidate_id = str(row.get("candidate_id") or "").strip()
    if not candidate_id:
        candidate_id = sha256(
            f"{strategy_id}|{symbol}|{signal_ts.isoformat()}|{direction}".encode("utf-8")
        ).hexdigest()

    entry = _number(row, "entry_price", _number(row, "entry_open"))
    signal_close = _number(row, "signal_close", entry)
    target_price = _number(row, "target")
    failed_level = _number(row, "failed_level", signal_close)
    reclaim_level = _number(row, "reclaim_or_reject_level", signal_close)
    risk = _risk_distance(row)
    proxy_delta = 0.5
    proxy_net = _number(row, "proxy_option_net_pnl", _number(row, "net_pnl"))
    proxy_cost = _number(row, "proxy_option_execution_cost", _number(row, "costs"))
    net_r = proxy_net / max(risk * proxy_delta, 1e-12)
    friction_r = proxy_cost / max(risk * proxy_delta, 1e-12)
    local = signal_ts.tz_convert("Asia/Kolkata")
    minutes_since_open = max(0.0, float(local.hour * 60 + local.minute - (9 * 60 + 15)))
    angle = 2.0 * math.pi * minutes_since_open / 375.0
    planned_reward_r = abs(target_price - entry) / risk
    cost_margin = _number(row, "cost_hurdle_margin")

    target_hit = int(exit_reason == "TARGET")
    stop_hit = int(exit_reason in {"STOP_LOSS", "SAME_CANDLE_AMBIGUOUS_ASSUMED_STOP"})
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": candidate_id,
        "trade_key": str(row.get("decision_id") or candidate_id),
        "strategy_id": strategy_id,
        "symbol": symbol,
        "option_type": "CE" if direction == "LONG" else "PE",
        "decision_ts_epoch_ms": int(signal_ts.timestamp() * 1000),
        "feature_cutoff_ts_epoch_ms": int(signal_ts.timestamp() * 1000),
        "outcome_ts_epoch_ms": int(exit_ts.timestamp() * 1000),
        "session_date": local.date().isoformat(),
        "target": target_hit,
        "stop_hit": stop_hit,
        "exec_feasible": 0,
        "future_mfe_points": np.nan,
        "future_mae_points": np.nan,
        "future_net_r": float(net_r),
        "friction_r": float(friction_r),
        "direction_long": int(direction == "LONG"),
        "symbol_nifty": int(symbol == "NIFTY"),
        "symbol_banknifty": int(symbol == "BANKNIFTY"),
        "symbol_sensex": int(symbol == "SENSEX"),
        "setup_failed_breakdown_long": int(setup_type == "FAILED_BREAKDOWN_LONG"),
        "setup_failed_breakout_short": int(setup_type == "FAILED_BREAKOUT_SHORT"),
        "htf_bullish": int("BULLISH" in htf_regime),
        "htf_bearish": int("BEARISH" in htf_regime),
        "rejection_quality": _number(row, "rejection_quality"),
        "cost_hurdle_margin_r": float(cost_margin / risk),
        "planned_reward_r": float(planned_reward_r),
        "entry_gap_r": float((entry - signal_close) / risk),
        "failed_level_distance_r": float(abs(signal_close - failed_level) / risk),
        "reclaim_distance_r": float(abs(signal_close - reclaim_level) / risk),
        "wick_ratio": _number(row, "wick_ratio", _number(row, "rejection_quality")),
        "minutes_since_open": float(minutes_since_open),
        "time_sin": float(math.sin(angle)),
        "time_cos": float(math.cos(angle)),
        "entry_delay_bars": _number(row, "entry_delay_bars"),
        "time_stop_minutes": _number(row, "time_stop_minutes"),
        **SAFETY_CONTRACT,
    }


def build_replay_ledger_dataset(
    records: Iterable[Mapping[str, Any]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        try:
            row = _row_to_candidate(record)
            event_id = str(row["event_id"])
            if event_id in seen:
                rejected.append({"row_index": index, "reason": "duplicate_candidate_id", "event_id": event_id})
                continue
            seen.add(event_id)
            rows.append(row)
        except Exception as exc:
            rejected.append({"row_index": index, "reason": f"{type(exc).__name__}:{exc}"})
    if not rows:
        raise ValueError("replay_ledger_dataset_empty")
    dataset = pd.DataFrame(rows).sort_values(
        ["decision_ts_epoch_ms", "event_id"], kind="stable"
    ).reset_index(drop=True)
    validate_candidate_dataset(dataset)
    evidence = {
        "lane": REPLAY_LEDGER_LANE,
        "input_records": int(len(rows) + len(rejected)),
        "accepted_rows": int(len(rows)),
        "rejected_rows": int(len(rejected)),
        "rejections": rejected,
        "sessions": int(dataset["session_date"].nunique()),
        "symbols": sorted(str(value) for value in dataset["symbol"].unique()),
        "strategies": sorted(str(value) for value in dataset["strategy_id"].unique()),
        "positive_rows": int(dataset["target"].sum()),
        "positive_rate": float(dataset["target"].mean()),
        "execution_grade": False,
        "option_truth": "MOCKED_CONTRACT_PROXY_PNL",
        "candidate_lineage_available": True,
        "candidate_edge_certification_allowed": False,
        "model_authority": "STRATEGY_PROXY_SELECTOR_ONLY",
        "reason": "Candidate IDs and resolved replay outcomes are real lineage, but option contracts and PnL are proxy/mock and cannot certify option profitability.",
        **SAFETY_CONTRACT,
    }
    return dataset, evidence


__all__ = [
    "REPLAY_LEDGER_LANE",
    "REPLAY_LEDGER_REQUIRED_FEATURES",
    "build_replay_ledger_dataset",
    "load_jsonl_records",
]
