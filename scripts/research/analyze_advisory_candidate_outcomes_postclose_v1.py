#!/usr/bin/env python3
"""Causal post-close counterfactual outcomes for advisory/rejected candidates.

This tool is analysis-only. It never turns a rejected/advisory candidate into a
trade and never reports realized P&L. Only observations strictly after the
candidate decision timestamp are eligible. Exact option instrument identity is
required; missing fields remain unavailable rather than being imputed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "tradebot-advisory-counterfactual-outcomes-v1"


class AnalysisError(ValueError):
    pass


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _regular(path: Path, label: str) -> Path:
    absolute = path.expanduser().absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise AnalysisError(f"{label}_REGULAR_FILE_REQUIRED:{absolute}")
    return absolute.resolve()


def _load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    source = _regular(path, label)
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AnalysisError(f"{label}_JSON_INVALID:{line_no}") from exc
        if not isinstance(payload, Mapping):
            raise AnalysisError(f"{label}_ROW_NOT_OBJECT:{line_no}")
        rows.append(dict(payload))
    return rows


def _candidate_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("candidate_id") or row.get("trade_id"))


def _instrument(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    return _text(
        row.get("selected_option_instrument")
        or row.get("instrument_key")
        or metadata.get("selected_option_instrument")
        or metadata.get("instrument_key")
    )


def _expiry(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    return _text(row.get("expiry") or row.get("option_expiry") or metadata.get("expiry") or metadata.get("option_expiry"))


def _signal_epoch(row: Mapping[str, Any]) -> float | None:
    for key in ("signal_epoch", "decision_epoch", "created_at_epoch", "entry_epoch", "ts_epoch"):
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _price(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _direction(row: Mapping[str, Any]) -> str | None:
    raw = _text(row.get("direction") or row.get("side")).upper()
    if raw in {"BUY", "LONG", "BUY_CALL", "BUY_PUT", "CE", "PE"}:
        return "BUY"
    if raw in {"SELL", "SHORT", "SELL_CALL", "SELL_PUT"}:
        return "SELL"
    return None


def _counterfactual_one(candidate: Mapping[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    cid = _candidate_id(candidate)
    instrument = _instrument(candidate)
    expiry = _expiry(candidate)
    signal = _signal_epoch(candidate)
    direction = _direction(candidate)
    entry = _price(candidate, "entry_price", "entry")
    stop = _price(candidate, "stop_loss_price", "stop_loss", "sl")
    target = _price(candidate, "target_price", "target", "tp")
    timeout = _price(candidate, "timeout_epoch")

    base = {
        "candidate_id": cid or None,
        "instrument_key": instrument or None,
        "expiry": expiry or None,
        "signal_epoch": signal,
        "direction": direction,
        "entry_price": entry,
        "stop_loss_price": stop,
        "target_price": target,
        "source_stage_status": _text(candidate.get("stage_status") or candidate.get("status")) or None,
        "source_advisory": bool(candidate.get("advisory")),
        "source_execution_allowed": bool(candidate.get("execution_allowed")),
        "counterfactual_only": True,
        "realized_trade": False,
        "realized_pnl": None,
        "touch_is_realized_pnl": False,
    }
    missing = [name for name, value in (("candidate_id", cid), ("instrument_key", instrument), ("expiry", expiry), ("signal_epoch", signal), ("direction", direction), ("entry_price", entry), ("stop_loss_price", stop), ("target_price", target)) if value in (None, "")]
    if missing:
        return {**base, "outcome_status": "UNAVAILABLE_REQUIRED_FIELDS", "missing_fields": missing, "first_hit_epoch": None, "observation_count": 0}

    assert signal is not None and direction is not None and entry is not None and stop is not None and target is not None
    if direction == "BUY" and not stop < entry < target:
        return {**base, "outcome_status": "INVALID_RISK_MODEL", "missing_fields": [], "first_hit_epoch": None, "observation_count": 0}
    if direction == "SELL" and not target < entry < stop:
        return {**base, "outcome_status": "INVALID_RISK_MODEL", "missing_fields": [], "first_hit_epoch": None, "observation_count": 0}

    eligible = []
    for row in observations:
        if _text(row.get("instrument_key") or row.get("selected_option_instrument")) != instrument:
            continue
        ts = _num(row.get("observed_epoch") if row.get("observed_epoch") is not None else row.get("ts_epoch"))
        ltp = _num(row.get("ltp"))
        if ts is None or ltp is None or ts <= signal:  # strict future-only rule
            continue
        if timeout is not None and ts > timeout:
            continue
        eligible.append((ts, ltp, _num(row.get("bid")), _num(row.get("ask"))))
    eligible.sort(key=lambda item: (item[0], item[1]))
    if not eligible:
        return {**base, "outcome_status": "NO_FUTURE_OBSERVATIONS", "missing_fields": [], "first_hit_epoch": None, "observation_count": 0}

    by_ts: dict[float, list[tuple[float, float | None, float | None]]] = {}
    for ts, ltp, bid, ask in eligible:
        by_ts.setdefault(ts, []).append((ltp, bid, ask))

    first_status = None
    first_epoch = None
    for ts in sorted(by_ts):
        target_hit = False
        stop_hit = False
        for ltp, bid, ask in by_ts[ts]:
            if direction == "BUY":
                target_hit |= ltp >= target or (ask is not None and ask >= target)
                stop_hit |= ltp <= stop or (bid is not None and bid <= stop)
            else:
                target_hit |= ltp <= target or (bid is not None and bid <= target)
                stop_hit |= ltp >= stop or (ask is not None and ask >= stop)
        if target_hit or stop_hit:
            first_epoch = ts
            first_status = "AMBIGUOUS_SAME_TIMESTAMP" if target_hit and stop_hit else ("TARGET_TOUCHED" if target_hit else "STOP_TOUCHED")
            break

    status = first_status or ("TIMEOUT_NO_TOUCH" if timeout is not None else "NO_TOUCH_IN_SUPPLIED_WINDOW")
    prices = [row[1] for row in eligible]
    return {
        **base,
        "outcome_status": status,
        "missing_fields": [],
        "first_hit_epoch": first_epoch,
        "observation_count": len(eligible),
        "first_future_observation_epoch": eligible[0][0],
        "last_observation_epoch": eligible[-1][0],
        "max_observed_ltp": max(prices),
        "min_observed_ltp": min(prices),
    }


def analyze(candidate_rows: Iterable[Mapping[str, Any]], observation_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = [dict(row) for row in candidate_rows]
    observations = [dict(row) for row in observation_rows]
    ids = [_candidate_id(row) for row in candidates]
    nonempty = [cid for cid in ids if cid]
    if len(nonempty) != len(set(nonempty)):
        raise AnalysisError("DUPLICATE_CANDIDATE_ID")
    rows = [_counterfactual_one(row, observations) for row in candidates]
    return {
        "schema": SCHEMA,
        "status": "POSTCLOSE_COUNTERFACTUAL_ANALYSIS_COMPLETE",
        "candidate_count": len(candidates),
        "outcomes": rows,
        "strict_future_only": True,
        "rejected_candidate_is_trade": False,
        "touch_is_realized_pnl": False,
        "realized_pnl_computed": False,
        "missing_values_coerced_to_zero": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "structural_edge_certified": False,
    }


def _write_once(path: Path, payload: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        target.resolve().relative_to(repo_root.resolve())
        raise AnalysisError("OUTPUT_MUST_BE_EXTERNAL_TO_REPO")
    except ValueError:
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AnalysisError("OUTPUT_ALREADY_EXISTS") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = analyze(_load_jsonl(args.candidates, "CANDIDATES"), _load_jsonl(args.observations, "OBSERVATIONS"))
    _write_once(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
