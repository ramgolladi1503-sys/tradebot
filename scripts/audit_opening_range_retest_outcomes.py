#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
HORIZONS = (1, 3, 5, 10, 15, 30)
EXPECTED_CANDIDATE_COUNT = 2215
EXPECTED_CANDIDATE_HASH = "53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24"
EXPECTED_SOURCE_COUNT = 1512
EXPECTED_SOURCE_HASH = "cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse(value: Any, *, source: bool = False) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text.replace(" ", "T"))
    if dt.tzinfo is None:
        if not source:
            raise ValueError(f"naive_timestamp:{value}")
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def _canon(dt: datetime) -> str:
    return dt.astimezone(IST).replace(microsecond=0).isoformat()


def _candidate_from_row(row: dict[str, Any]) -> dict[str, str]:
    semantic = dict(row.get("semantic_payload") or {})
    symbol = str(row.get("symbol") or semantic.get("symbol") or "").upper()
    session = str(row.get("session_date") or "")
    setup_id = str(row.get("setup_id") or semantic.get("setup_id") or "")
    return {
        "candidate_id": str(row.get("candidate_hash") or setup_id),
        "candidate_hash": str(row.get("candidate_hash") or setup_id),
        "session_key": str(row.get("session_key") or f"{session}:{symbol}"),
        "symbol": symbol,
        "direction": str(row.get("direction") or semantic.get("direction") or "").upper(),
        "proposal_ready_at": _canon(_parse(row.get("proposal_ready_at_iso") or semantic.get("proposal_ready_at_iso"))),
    }


def _resolve_source(source: dict[str, Any]) -> Path:
    logical = PROJECT_ROOT / str(source["logical_path"])
    return logical if logical.exists() else Path(str(source["absolute_path"]))


def _verify_sources(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for source in manifest.get("records") or []:
        path = _resolve_source(source)
        if not path.exists():
            raise ValueError(f"missing_source:{source.get('logical_path')}")
        if _sha_file(path) != str(source.get("sha256")):
            raise ValueError(f"source_sha_mismatch:{source.get('logical_path')}")
        if path.stat().st_size != int(source.get("byte_size") or -1):
            raise ValueError(f"source_size_mismatch:{source.get('logical_path')}")
        frame = pd.read_parquet(path)
        for column in ("timestamp", "symbol", "open", "high", "low", "close", "volume"):
            if column not in frame.columns:
                raise ValueError(f"missing_source_column:{source.get('logical_path')}:{column}")
        if len(frame) != int(source.get("row_count") or -1):
            raise ValueError(f"source_row_count_mismatch:{source.get('logical_path')}")
        timestamps = [_parse(value, source=True) for value in frame["timestamp"]]
        if len(timestamps) != len(set(timestamps)):
            raise ValueError(f"duplicate_source_timestamp:{source.get('logical_path')}")
        if any(curr <= prev for prev, curr in zip(timestamps, timestamps[1:])):
            raise ValueError(f"non_monotonic_source_timestamp:{source.get('logical_path')}")
        if any(ts.date().isoformat() != str(source.get("session_date")) for ts in timestamps):
            raise ValueError(f"wrong_source_session:{source.get('logical_path')}")
        expected_symbol = str(source.get("symbol") or "").upper()
        actual_symbols = {_normalize_source_symbol(value) for value in frame["symbol"].dropna().unique()}
        if actual_symbols and actual_symbols != {expected_symbol}:
            raise ValueError(f"source_symbol_mismatch:{source.get('logical_path')}")
        highs = frame["high"].astype(float)
        lows = frame["low"].astype(float)
        opens = frame["open"].astype(float)
        closes = frame["close"].astype(float)
        if (pd.concat([opens, highs, lows, closes], axis=1) <= 0).any().any():
            raise ValueError(f"invalid_source_price:{source.get('logical_path')}")
        if (highs < pd.concat([opens, lows, closes], axis=1).max(axis=1)).any():
            raise ValueError(f"invalid_source_high:{source.get('logical_path')}")
        if (lows > pd.concat([opens, highs, closes], axis=1).min(axis=1)).any():
            raise ValueError(f"invalid_source_low:{source.get('logical_path')}")
        key = f"{source.get('session_date')}:{expected_symbol}"
        out[key] = {
            "logical_path": str(source["logical_path"]),
            "sha256": str(source["sha256"]),
            "byte_size": int(source["byte_size"]),
            "row_count": int(source["row_count"]),
            "frame": frame.sort_values("timestamp").reset_index(drop=True),
        }
    return out


def _normalize_source_symbol(value: Any) -> str:
    text = str(value).upper()
    if "NIFTY 50" in text:
        return "NIFTY"
    if "NIFTY BANK" in text or "BANKNIFTY" in text:
        return "BANKNIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    return text


def _directional(direction: str, entry: float, price: float) -> float:
    raw = (float(price) - float(entry)) / float(entry)
    return raw if direction == "BUY_CALL" else -raw


def _prefix_hash(frame: pd.DataFrame, proposal: datetime) -> str:
    rows = []
    for row in frame.to_dict(orient="records"):
        ts = _parse(row["timestamp"], source=True)
        if ts <= proposal:
            rows.append({"timestamp": _canon(ts), "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]), "close": float(row["close"])})
    return _hash(rows)


def _legal_entry(frame: pd.DataFrame, proposal: datetime) -> int | None:
    for i, value in enumerate(frame["timestamp"]):
        if _parse(value, source=True) > proposal:
            return i
    return None


def _terminal(frame: pd.DataFrame, entry_index: int, horizon: int) -> tuple[datetime, int | None]:
    entry_ts = _parse(frame.iloc[entry_index]["timestamp"], source=True)
    expected = entry_ts + timedelta(minutes=int(horizon) - 1)
    for i in range(entry_index, len(frame)):
        ts = _parse(frame.iloc[i]["timestamp"], source=True)
        if ts == expected:
            return expected, i
        if ts > expected:
            return expected, None
    return expected, None


def _mfe_mae(direction: str, entry: float, window: pd.DataFrame) -> tuple[float, int, float, int]:
    best = worst = None
    best_t = worst_t = None
    entry_ts = _parse(window.iloc[0]["timestamp"], source=True)
    for row in window.to_dict(orient="records"):
        ts = _parse(row["timestamp"], source=True)
        favorable_price = float(row["high"]) if direction == "BUY_CALL" else float(row["low"])
        adverse_price = float(row["low"]) if direction == "BUY_CALL" else float(row["high"])
        favorable = _directional(direction, entry, favorable_price)
        adverse = _directional(direction, entry, adverse_price)
        if best is None or favorable > best:
            best = favorable
            best_t = int((ts - entry_ts).total_seconds() // 60)
        if worst is None or adverse < worst:
            worst = adverse
            worst_t = int((ts - entry_ts).total_seconds() // 60)
    assert best is not None and worst is not None and best_t is not None and worst_t is not None
    return best, best_t, worst, worst_t


def _path_event(direction: str, entry: float, window: pd.DataFrame, *, stop_return: float, target_return: float) -> str:
    for row in window.to_dict(orient="records"):
        favorable_price = float(row["high"]) if direction == "BUY_CALL" else float(row["low"])
        adverse_price = float(row["low"]) if direction == "BUY_CALL" else float(row["high"])
        hit_target = _directional(direction, entry, favorable_price) >= target_return
        hit_stop = _directional(direction, entry, adverse_price) <= -abs(stop_return)
        if hit_target and hit_stop:
            return "AMBIGUOUS_SAME_BAR"
        if hit_target:
            return "TARGET_FIRST"
        if hit_stop:
            return "STOP_FIRST"
    return "NEITHER"


def _expected_record(candidate: dict[str, str], source: dict[str, Any] | None, *, stop_return: float, target_return: float) -> dict[str, Any]:
    proposal = _parse(candidate["proposal_ready_at"])
    if source is None:
        return {"candidate_status": "MISSING_SOURCE_SESSION"}
    frame = source["frame"]
    entry_index = _legal_entry(frame, proposal)
    if entry_index is None:
        return {"candidate_status": "NO_LEGAL_ENTRY", "source_prefix_hash": _prefix_hash(frame, proposal)}
    entry = frame.iloc[entry_index]
    entry_ts = _parse(entry["timestamp"], source=True)
    entry_price = float(entry["open"])
    horizons = {}
    max_h = 0
    for horizon in HORIZONS:
        expected, terminal_index = _terminal(frame, entry_index, horizon)
        if terminal_index is None:
            horizons[str(horizon)] = {"status": "INSUFFICIENT_HORIZON", "expected_terminal_timestamp": _canon(expected)}
            continue
        max_h = horizon
        terminal = frame.iloc[terminal_index]
        window = frame.iloc[entry_index : terminal_index + 1]
        mfe, mfe_t, mae, mae_t = _mfe_mae(candidate["direction"], entry_price, window)
        horizons[str(horizon)] = {
            "status": "MEASURED",
            "expected_terminal_timestamp": _canon(expected),
            "actual_terminal_timestamp": _canon(_parse(terminal["timestamp"], source=True)),
            "forward_return": _directional(candidate["direction"], entry_price, float(terminal["close"])),
            "mfe": mfe,
            "mae": mae,
            "elapsed_minutes_to_mfe": mfe_t,
            "elapsed_minutes_to_mae": mae_t,
            "path_event": _path_event(candidate["direction"], entry_price, window, stop_return=stop_return, target_return=target_return),
        }
    return {
        "candidate_status": "MEASURED",
        "legal_entry_timestamp": _canon(entry_ts),
        "entry_reference_price": entry_price,
        "session_close_return": _directional(candidate["direction"], entry_price, float(frame.iloc[-1]["close"])),
        "maximum_legal_horizon": max_h,
        "source_prefix_hash": _prefix_hash(frame, proposal),
        "horizons": horizons,
        "verified_source_sha256": source["sha256"],
        "source_byte_size": source["byte_size"],
        "source_row_count": source["row_count"],
        "source_logical_path": source["logical_path"],
    }


def _compare_float(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return abs(float(left) - float(right)) <= 1e-12


def _audit_records(records: list[dict[str, Any]], ledger: dict[str, Any], sources: dict[str, dict[str, Any]], *, stop_return: float, target_return: float) -> list[str]:
    failures: list[str] = []
    by_id = {str(record.get("candidate_id")): record for record in records}
    if len(by_id) != len(records):
        failures.append("candidate_identity_not_unique")
    for row in ledger.get("records") or []:
        candidate = _candidate_from_row(row)
        record = by_id.get(candidate["candidate_id"])
        if record is None:
            failures.append(f"missing_candidate_record:{candidate['candidate_id']}")
            continue
        expected = _expected_record(candidate, sources.get(candidate["session_key"]), stop_return=stop_return, target_return=target_return)
        for field in ("candidate_status", "legal_entry_timestamp", "maximum_legal_horizon", "source_prefix_hash", "verified_source_sha256", "source_byte_size", "source_row_count", "source_logical_path"):
            if field in expected and record.get(field) != expected[field]:
                failures.append(f"field_mismatch:{candidate['candidate_id']}:{field}")
                break
        if "entry_reference_price" in expected and not _compare_float(record.get("entry_reference_price"), expected["entry_reference_price"]):
            failures.append(f"field_mismatch:{candidate['candidate_id']}:entry_reference_price")
            continue
        if "session_close_return" in expected and not _compare_float(record.get("session_close_return"), expected["session_close_return"]):
            failures.append(f"field_mismatch:{candidate['candidate_id']}:session_close_return")
            continue
        for horizon, expected_horizon in dict(expected.get("horizons") or {}).items():
            actual = dict(record.get("horizons") or {}).get(horizon)
            if actual is None:
                failures.append(f"missing_horizon:{candidate['candidate_id']}:{horizon}")
                break
            for field, expected_value in expected_horizon.items():
                actual_value = actual.get(field)
                if isinstance(expected_value, float):
                    if not _compare_float(actual_value, expected_value):
                        failures.append(f"horizon_mismatch:{candidate['candidate_id']}:{horizon}:{field}")
                        break
                elif actual_value != expected_value:
                    failures.append(f"horizon_mismatch:{candidate['candidate_id']}:{horizon}:{field}")
                    break
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently audit corrected ORB outcome artifacts.")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--compare-artifact-dir", type=Path)
    parser.add_argument("--candidate-ledger", type=Path, default=PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_causal_replay_candidate_ledger_v1.json")
    parser.add_argument("--source-manifest", type=Path, default=PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_causal_replay_source_manifest_v1.json")
    args = parser.parse_args()
    summary = _load(args.artifact_dir / "opening_range_retest_outcome_summary_v1.json")
    records = list(_load(args.artifact_dir / "opening_range_retest_outcome_records_v1.json").get("records") or [])
    contract = _load(args.artifact_dir / "opening_range_retest_outcome_contract_v1.json")
    ledger = _load(args.candidate_ledger)
    manifest = _load(args.source_manifest)
    failures: list[str] = []
    if ledger.get("candidate_count") != EXPECTED_CANDIDATE_COUNT or ledger.get("candidate_semantic_hash") != EXPECTED_CANDIDATE_HASH:
        failures.append("certified_candidate_identity_mismatch")
    if len(manifest.get("records") or []) != EXPECTED_SOURCE_COUNT or dict(manifest.get("selection_summary") or {}).get("semantic_hash") != EXPECTED_SOURCE_HASH:
        failures.append("certified_source_identity_mismatch")
    sources = _verify_sources(manifest)
    if len(sources) != EXPECTED_SOURCE_COUNT:
        failures.append("source_count_mismatch")
    if len(records) != EXPECTED_CANDIDATE_COUNT or summary.get("candidate_count") != EXPECTED_CANDIDATE_COUNT:
        failures.append("candidate_count_mismatch")
    failures.extend(_audit_records(records, ledger, sources, stop_return=float(contract["stop_return"]), target_return=float(contract["target_return"])))
    candidate_status_counts = dict(sorted(Counter(str(record.get("candidate_status")) for record in records).items()))
    if summary.get("candidate_status_counts") != candidate_status_counts:
        failures.append("summary_candidate_status_counts_mismatch")
    record_hash = _hash(sorted(records, key=lambda item: str(item.get("candidate_id") or "")))
    if summary.get("candidate_record_semantic_hash") != record_hash:
        failures.append("candidate_record_semantic_hash_mismatch")
    compare_record_hash = None
    compare_summary_hash = None
    if args.compare_artifact_dir:
        other_summary = _load(args.compare_artifact_dir / "opening_range_retest_outcome_summary_v1.json")
        other_records = list(_load(args.compare_artifact_dir / "opening_range_retest_outcome_records_v1.json").get("records") or [])
        compare_record_hash = _hash(sorted(other_records, key=lambda item: str(item.get("candidate_id") or "")))
        compare_summary_hash = other_summary.get("strategy_semantic_summary_hash")
        if compare_record_hash != record_hash:
            failures.append("comparison_record_hash_mismatch")
        if compare_summary_hash != summary.get("strategy_semantic_summary_hash"):
            failures.append("comparison_summary_hash_mismatch")
    verdict = "ORB_OUTCOME_AUDIT_READY" if not failures else "AUDIT_INVALID"
    print(
        json.dumps(
            {
                "verdict": verdict,
                "candidate_count": len(records),
                "candidate_record_semantic_hash": record_hash,
                "strategy_semantic_summary_hash": summary.get("strategy_semantic_summary_hash"),
                "compare_candidate_record_semantic_hash": compare_record_hash,
                "compare_strategy_semantic_summary_hash": compare_summary_hash,
                "failures": failures[:25],
                "failure_count": len(failures),
            },
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
