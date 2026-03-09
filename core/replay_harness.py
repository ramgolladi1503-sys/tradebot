from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.decision_builder import build_decision
from core.paths import data_root
from core.time_utils import now_ist, now_utc_epoch


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _sanitize_day(day: str) -> str:
    text = str(day or "").strip()
    if not text:
        return now_ist().strftime("%Y%m%d")
    return "".join(ch for ch in text if ch.isdigit())[:8] or now_ist().strftime("%Y%m%d")


def replay_day_dir(day: str, *, base_dir: Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else (data_root() / "replay")
    out = root / _sanitize_day(day)
    out.mkdir(parents=True, exist_ok=True)
    return out


def recording_day_dir(day: str, *, base_dir: Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else (data_root() / "recordings")
    out = root / _sanitize_day(day)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def record_snapshot_decision(
    *,
    snapshot: dict[str, Any],
    meta: dict[str, Any],
    market: dict[str, Any],
    signals: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    strategy_family: str | None = None,
    day: str | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    ts_epoch = (
        _safe_float(meta.get("ts_epoch"))
        or _safe_float(snapshot.get("timestamp_epoch"))
        or float(now_utc_epoch())
    )
    day_key = _sanitize_day(day or now_ist().strftime("%Y%m%d"))
    day_dir = replay_day_dir(day_key, base_dir=base_dir)
    recording_dir = recording_day_dir(day_key, base_dir=base_dir)
    snapshot_path = day_dir / "snapshots.jsonl"
    decision_path = day_dir / "decisions.jsonl"
    session_path = recording_dir / "session.jsonl"

    decision = build_decision(
        meta=meta,
        market=market,
        signals=signals or {},
        strategy=strategy or {},
        risk=risk or {},
        outcome=outcome or {},
        strategy_family=strategy_family,
        decision_snapshot=snapshot,
    )
    decision_payload = decision.to_dict()
    recorded = {
        "decision_id": str(decision_payload.get("decision_id")),
        "reject_reasons": list((decision_payload.get("outcome") or {}).get("reject_reasons") or []),
    }

    snapshot_row = {
        "ts_epoch": float(ts_epoch),
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot": dict(snapshot),
    }
    decision_row = {
        "ts_epoch": float(ts_epoch),
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot": dict(snapshot),
        "decision_input": {
            "meta": dict(meta),
            "market": dict(market),
            "signals": dict(signals or {}),
            "strategy": dict(strategy or {}),
            "risk": dict(risk or {}),
            "outcome": dict(outcome or {}),
            "strategy_family": strategy_family,
        },
        "recorded": recorded,
    }

    _append_jsonl(snapshot_path, snapshot_row)
    _append_jsonl(decision_path, decision_row)
    _append_jsonl(
        session_path,
        {
            "event_type": "snapshot_decision",
            "ts_epoch": float(ts_epoch),
            "snapshot_id": snapshot.get("snapshot_id"),
            "snapshot": dict(snapshot),
            "decision_input": dict(decision_row.get("decision_input") or {}),
            "recorded": dict(recorded),
        },
    )
    return {
        "day_dir": str(day_dir),
        "snapshot_path": str(snapshot_path),
        "decision_path": str(decision_path),
        "session_path": str(session_path),
        "recorded": recorded,
    }


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            text = str(line).strip()
            if not text:
                continue
            yield idx, json.loads(text)


def replay_from_file(
    path: Path,
    *,
    start_ts: float | None = None,
    end_ts: float | None = None,
    strict: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, payload in _iter_jsonl(Path(path)):
        if not isinstance(payload, dict):
            continue
        ts_epoch = (
            _safe_float(payload.get("ts_epoch"))
            or _safe_float((payload.get("decision_input") or {}).get("meta", {}).get("ts_epoch"))
            or _safe_float((payload.get("snapshot") or {}).get("timestamp_epoch"))
            or 0.0
        )
        if start_ts is not None and ts_epoch < float(start_ts):
            continue
        if end_ts is not None and ts_epoch > float(end_ts):
            continue

        decision_input = dict(payload.get("decision_input") or {})
        snapshot = dict(payload.get("snapshot") or {})
        meta_payload = dict(decision_input.get("meta") or {})
        meta_payload["ts_epoch"] = float(ts_epoch)
        decision = build_decision(
            meta=meta_payload,
            market=dict(decision_input.get("market") or {}),
            signals=dict(decision_input.get("signals") or {}),
            strategy=dict(decision_input.get("strategy") or {}),
            risk=dict(decision_input.get("risk") or {}),
            outcome=dict(decision_input.get("outcome") or {}),
            strategy_family=decision_input.get("strategy_family"),
            decision_snapshot=snapshot,
        )
        replayed = decision.to_dict()
        actual_id = str(replayed.get("decision_id"))
        actual_reasons = list((replayed.get("outcome") or {}).get("reject_reasons") or [])

        recorded = dict(payload.get("recorded") or {})
        expected_id = str(recorded.get("decision_id") or "")
        expected_reasons = list(recorded.get("reject_reasons") or [])
        id_match = bool(expected_id) and expected_id == actual_id
        reasons_match = expected_reasons == actual_reasons
        matched = bool(id_match and reasons_match)
        row = {
            "line_no": int(line_no),
            "ts_epoch": float(ts_epoch),
            "decision_id": actual_id,
            "reject_reasons": actual_reasons,
            "expected_decision_id": expected_id,
            "expected_reject_reasons": expected_reasons,
            "match": matched,
        }
        rows.append(row)
        if strict and not matched:
            raise ValueError(
                f"deterministic replay mismatch line={line_no} "
                f"decision_id expected={expected_id} actual={actual_id} "
                f"reject_reasons expected={expected_reasons} actual={actual_reasons}"
            )
    return rows
