from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION
from .dataset import validate_candidate_dataset


HISTORICAL_OPTION_LANE = "KITE_UNDERLYING_UPSTOX_EXPIRED_OPTION_RECONSTRUCTION"
HISTORICAL_OPTION_REQUIRED_FEATURES = (
    "direction_put",
    "signal_underlying_price",
    "candidate_raw_score",
    "candidate_confidence_score",
    "candidate_price_structure_score",
    "candidate_blocker_count",
    "candidate_warning_count",
    "minutes_since_open",
    "time_sin",
    "time_cos",
    "expiry_days",
    "requested_entry_delay_minutes",
    "atm_distance_steps",
)


class HistoricalOptionDataError(ValueError):
    """Raised when historical candidate-to-option evidence is contradictory."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: str | Path, *, required: set[str], kind: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"{kind}_missing:{source}")
    frame = pd.read_csv(source)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise HistoricalOptionDataError(f"{kind}_columns_missing:{','.join(missing)}")
    return frame, {
        "kind": kind,
        "path": str(source),
        "sha256": _sha256_file(source),
        "bytes": int(source.stat().st_size),
        "rows": int(frame.shape[0]),
    }


def load_canonical_intents(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    return _read_csv(
        path,
        required={
            "strategy_id",
            "underlying",
            "signal_timestamp",
            "earliest_entry_timestamp",
            "direction",
            "signal_time_underlying_price",
            "intended_option_type",
            "signal_identity_hash",
        },
        kind="canonical_option_intents",
    )


def load_option_trade_ledger(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    return _read_csv(
        path,
        required={
            "strategy_id",
            "signal_identity_hash",
            "signal_timestamp",
            "underlying",
            "option_type",
            "expiry",
            "atm_strike",
            "strike",
            "entry_timestamp",
            "entry_price",
            "exit_timestamp",
            "exit_price",
            "exit_reason",
            "unit_net_pnl",
            "unit_friction_cost",
            "net_return_pct",
            "partition",
        },
        kind="expired_option_trade_ledger",
    )


def load_option_replay_blockers(path: str | Path | None) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    if path is None:
        return pd.DataFrame(), None
    return _read_csv(
        path,
        required={"signal_identity_hash", "blocker_class", "exact_reason"},
        kind="expired_option_replay_blockers",
    )


def _number(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
    except Exception:
        return float(default)
    return value if math.isfinite(value) else float(default)


def _timestamp(value: Any, *, field: str) -> pd.Timestamp:
    stamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(stamp):
        raise HistoricalOptionDataError(f"timestamp_invalid:{field}")
    return pd.Timestamp(stamp)


def _json_list_count(value: Any) -> int:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0
    if isinstance(value, (list, tuple)):
        return len(value)
    text = str(value).strip()
    if not text:
        return 0
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return 1
    return len(parsed) if isinstance(parsed, list) else 1


def _strike_step(underlying: str) -> float:
    return 50.0 if str(underlying).upper() == "NIFTY" else 100.0


def _candidate_row(
    intent: Mapping[str, Any],
    trade: Mapping[str, Any],
    *,
    stop_loss_pct: float,
) -> dict[str, Any]:
    signal_ts = _timestamp(intent.get("signal_timestamp"), field="signal_timestamp")
    earliest_entry_ts = _timestamp(
        intent.get("earliest_entry_timestamp"), field="earliest_entry_timestamp"
    )
    entry_ts = _timestamp(trade.get("entry_timestamp"), field="entry_timestamp")
    exit_ts = _timestamp(trade.get("exit_timestamp"), field="exit_timestamp")
    trade_signal_ts = _timestamp(trade.get("signal_timestamp"), field="trade_signal_timestamp")
    if abs((trade_signal_ts - signal_ts).total_seconds()) > 1.0:
        raise HistoricalOptionDataError("intent_trade_signal_timestamp_mismatch")
    if earliest_entry_ts <= signal_ts:
        raise HistoricalOptionDataError("requested_entry_not_after_signal")
    if entry_ts < earliest_entry_ts or entry_ts <= signal_ts:
        raise HistoricalOptionDataError("option_entry_not_causal")
    if exit_ts <= entry_ts:
        raise HistoricalOptionDataError("option_exit_not_after_entry")

    identity = str(intent.get("signal_identity_hash") or "").strip()
    if not identity:
        raise HistoricalOptionDataError("signal_identity_hash_empty")
    if identity != str(trade.get("signal_identity_hash") or "").strip():
        raise HistoricalOptionDataError("intent_trade_identity_mismatch")

    strategy_id = str(intent.get("strategy_id") or "UNKNOWN").strip().upper()
    trade_strategy_id = str(trade.get("strategy_id") or "UNKNOWN").strip().upper()
    if strategy_id != trade_strategy_id:
        raise HistoricalOptionDataError("intent_trade_strategy_mismatch")
    underlying = str(intent.get("underlying") or "UNKNOWN").strip().upper()
    if underlying != str(trade.get("underlying") or "UNKNOWN").strip().upper():
        raise HistoricalOptionDataError("intent_trade_underlying_mismatch")
    option_type = str(intent.get("intended_option_type") or "").strip().upper()
    if option_type != str(trade.get("option_type") or "").strip().upper():
        raise HistoricalOptionDataError("intent_trade_option_type_mismatch")

    entry_price = _number(trade, "entry_price")
    if entry_price <= 0:
        raise HistoricalOptionDataError("option_entry_price_non_positive")
    unit_net_pnl = _number(trade, "unit_net_pnl")
    unit_friction = max(0.0, _number(trade, "unit_friction_cost"))
    risk_points = entry_price * float(stop_loss_pct)
    if risk_points <= 0:
        raise HistoricalOptionDataError("option_risk_points_non_positive")

    expiry = pd.Timestamp(str(trade.get("expiry"))).date()
    expiry_days = (expiry - signal_ts.tz_convert("Asia/Kolkata").date()).days
    if expiry_days < 0:
        raise HistoricalOptionDataError("option_expired_before_signal")

    atm_strike = _number(trade, "atm_strike")
    strike = _number(trade, "strike")
    strike_distance = abs(strike - atm_strike)
    step = _strike_step(underlying)
    local = signal_ts.tz_convert("Asia/Kolkata")
    minutes_since_open = float(local.hour * 60 + local.minute - (9 * 60 + 15))
    if minutes_since_open < 0 or minutes_since_open > 375:
        raise HistoricalOptionDataError("signal_outside_regular_session")
    angle = 2.0 * math.pi * minutes_since_open / 375.0
    requested_delay = (earliest_entry_ts - signal_ts).total_seconds() / 60.0
    exit_reason = str(trade.get("exit_reason") or "").strip().lower()

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": identity,
        "trade_key": identity,
        "strategy_id": strategy_id,
        "symbol": underlying,
        "option_type": option_type,
        "decision_ts_epoch_ms": int(signal_ts.timestamp() * 1000),
        "feature_cutoff_ts_epoch_ms": int(signal_ts.timestamp() * 1000),
        "outcome_ts_epoch_ms": int(exit_ts.timestamp() * 1000),
        "session_date": local.date().isoformat(),
        "target": int(unit_net_pnl > 0),
        "stop_hit": int(exit_reason == "stop"),
        "exec_feasible": 1,
        "future_mfe_points": np.nan,
        "future_mae_points": np.nan,
        "future_net_r": float(unit_net_pnl / risk_points),
        "friction_r": float(unit_friction / risk_points),
        "direction_put": int(option_type == "PE"),
        "signal_underlying_price": _number(intent, "signal_time_underlying_price"),
        "candidate_raw_score": _number(intent, "candidate_raw_score"),
        "candidate_confidence_score": _number(intent, "candidate_confidence_score"),
        "candidate_price_structure_score": _number(
            intent, "candidate_price_structure_score"
        ),
        "candidate_blocker_count": _json_list_count(intent.get("candidate_blockers")),
        "candidate_warning_count": _json_list_count(intent.get("candidate_warnings")),
        "minutes_since_open": minutes_since_open,
        "time_sin": float(math.sin(angle)),
        "time_cos": float(math.cos(angle)),
        "expiry_days": float(expiry_days),
        "requested_entry_delay_minutes": float(requested_delay),
        "atm_distance_steps": float(strike_distance / step),
        "match_quality": "EXACT_ATM" if strike_distance <= 1e-9 else "NEAREST_STRIKE_PROXY",
        "source_partition": str(trade.get("partition") or "").strip().lower(),
        **SAFETY_CONTRACT,
    }


def build_historical_option_datasets(
    intents: pd.DataFrame,
    trades: pd.DataFrame,
    blockers: pd.DataFrame | None = None,
    *,
    stop_loss_pct: float = 0.25,
    nearest_proxy_max_points: float = 100.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not 0 < stop_loss_pct < 1:
        raise ValueError("stop_loss_pct_invalid")
    if nearest_proxy_max_points <= 0:
        raise ValueError("nearest_proxy_max_points_invalid")

    intent_hashes = intents["signal_identity_hash"].astype(str).str.strip()
    if intent_hashes.eq("").any():
        raise HistoricalOptionDataError("intent_identity_empty")
    if intent_hashes.duplicated().any():
        raise HistoricalOptionDataError("duplicate_intent_identity")
    trade_hashes = trades["signal_identity_hash"].astype(str).str.strip()
    if trade_hashes.eq("").any():
        raise HistoricalOptionDataError("trade_identity_empty")
    if trade_hashes.duplicated().any():
        raise HistoricalOptionDataError("duplicate_trade_identity")

    trade_by_hash = {
        str(row["signal_identity_hash"]).strip(): row
        for row in trades.to_dict("records")
    }
    blocker_counts: dict[str, int] = {}
    blocker_hashes: set[str] = set()
    if blockers is not None and not blockers.empty:
        for row in blockers.to_dict("records"):
            identity = str(row.get("signal_identity_hash") or "").strip()
            if identity:
                blocker_hashes.add(identity)
            blocker_class = str(row.get("blocker_class") or "UNKNOWN").strip().upper()
            blocker_counts[blocker_class] = blocker_counts.get(blocker_class, 0) + 1

    exact_rows: list[dict[str, Any]] = []
    proxy_rows: list[dict[str, Any]] = []
    unmatched_hashes: list[str] = []
    rejected_distance_hashes: list[str] = []
    for intent in intents.sort_values("signal_timestamp", kind="stable").to_dict("records"):
        identity = str(intent["signal_identity_hash"]).strip()
        trade = trade_by_hash.get(identity)
        if trade is None:
            unmatched_hashes.append(identity)
            continue
        row = _candidate_row(intent, trade, stop_loss_pct=stop_loss_pct)
        if row["match_quality"] == "EXACT_ATM":
            exact_rows.append(row)
            continue
        distance_points = float(row["atm_distance_steps"]) * _strike_step(row["symbol"])
        if distance_points <= nearest_proxy_max_points + 1e-9:
            proxy_rows.append(row)
        else:
            rejected_distance_hashes.append(identity)

    exact = pd.DataFrame(exact_rows)
    proxy = pd.DataFrame(proxy_rows)
    for frame in (exact, proxy):
        if not frame.empty:
            frame.sort_values(
                ["decision_ts_epoch_ms", "event_id"], kind="stable", inplace=True
            )
            frame.reset_index(drop=True, inplace=True)
            validate_candidate_dataset(frame)

    overlap = set(exact.get("event_id", pd.Series(dtype=str))).intersection(
        set(proxy.get("event_id", pd.Series(dtype=str)))
    )
    if overlap:
        raise HistoricalOptionDataError("exact_proxy_identity_overlap")

    evidence = {
        "lane": HISTORICAL_OPTION_LANE,
        "schema_version": SCHEMA_VERSION,
        "input_intents": int(intents.shape[0]),
        "input_trades": int(trades.shape[0]),
        "exact_atm_rows": int(exact.shape[0]),
        "nearest_strike_proxy_rows": int(proxy.shape[0]),
        "unmatched_intents": int(len(unmatched_hashes)),
        "unmatched_intent_hashes": unmatched_hashes,
        "distance_rejected_rows": int(len(rejected_distance_hashes)),
        "distance_rejected_hashes": rejected_distance_hashes,
        "blocker_identity_count": int(len(blocker_hashes)),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "reconciled_intents": int(
            exact.shape[0]
            + proxy.shape[0]
            + len(unmatched_hashes)
            + len(rejected_distance_hashes)
        ),
        "reconciliation_passed": bool(
            int(intents.shape[0])
            == int(
                exact.shape[0]
                + proxy.shape[0]
                + len(unmatched_hashes)
                + len(rejected_distance_hashes)
            )
        ),
        "label_semantics": "POST_COST_POSITIVE_OPTION_OUTCOME",
        "future_net_r_semantics": "UNIT_NET_PNL_DIVIDED_BY_ENTRY_PREMIUM_TIMES_FROZEN_STOP_PERCENT",
        "exact_atm_authority": "REAL_UPSTOX_EXPIRED_OPTION_MINUTE_OHLC",
        "nearest_strike_authority": "SEPARATE_PROXY_ONLY_NOT_MIXED_WITH_EXACT_ATM",
        "candidate_lineage": "FROZEN_TRADEBOT_CANONICAL_INTENT_IDENTITY",
        "execution_grade": False,
        "execution_limitations": [
            "historical_bid_ask_unavailable",
            "depth_unavailable",
            "actual_fill_unavailable",
            "intrabar_path_ambiguous",
        ],
        "candidate_edge_research_allowed": bool(not exact.empty),
        "allowed_for_paper_execution": False,
        **SAFETY_CONTRACT,
    }
    if not evidence["reconciliation_passed"]:
        raise HistoricalOptionDataError("historical_option_reconciliation_failed")
    return exact, proxy, evidence


__all__ = [
    "HISTORICAL_OPTION_LANE",
    "HISTORICAL_OPTION_REQUIRED_FEATURES",
    "HistoricalOptionDataError",
    "build_historical_option_datasets",
    "load_canonical_intents",
    "load_option_replay_blockers",
    "load_option_trade_ledger",
]
