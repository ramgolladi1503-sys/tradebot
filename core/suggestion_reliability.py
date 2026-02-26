"""Migration note:
Periodic suggestion reliability SLO for PAPER/SIM/OFFHOURS.
Computes allowed->candidate ratio from decision events and emits DEGRADED with top reject reasons.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from config import config as cfg
from core.market_context import derive_market_context
from core.time_utils import now_ist, now_utc_epoch


def _decision_events_path() -> Path:
    return Path(str(getattr(cfg, "DECISION_LOG_PATH", "logs/desks/DEFAULT/decision_events.jsonl")))


def _reject_reasons_path() -> Path:
    return Path(str(getattr(cfg, "REJECT_REASONS_LOG_PATH", "logs/desks/DEFAULT/reject_reasons.jsonl")))


def _events_path() -> Path:
    return Path(str(getattr(cfg, "SUGGESTION_RELIABILITY_LOG_PATH", "logs/suggestion_reliability.jsonl")))


def _latest_path() -> Path:
    return Path(str(getattr(cfg, "SUGGESTION_RELIABILITY_LATEST_PATH", "logs/suggestion_reliability_latest.json")))


def _parse_ts_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        pass
    try:
        # ISO timestamp support.
        from datetime import datetime

        return float(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


def _iter_recent_rows(path: Path, *, window_start_epoch: float):
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = (
                    _parse_ts_epoch(row.get("timestamp_epoch"))
                    or _parse_ts_epoch(row.get("ts_epoch"))
                    or _parse_ts_epoch(row.get("ts"))
                )
                if ts is None or ts < float(window_start_epoch):
                    continue
                yield row
    except Exception:
        return


def evaluate_suggestion_reliability(
    *,
    market_context: dict[str, Any] | None = None,
    now_epoch: float | None = None,
    decision_events_path: Path | None = None,
    reject_reasons_path: Path | None = None,
) -> dict[str, Any]:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    window_sec = float(getattr(cfg, "SUGGESTION_RELIABILITY_WINDOW_SEC", 900.0))
    min_ratio = float(getattr(cfg, "SUGGESTION_RELIABILITY_MIN_RATIO", 0.15))
    min_allowed = max(1, int(getattr(cfg, "SUGGESTION_RELIABILITY_MIN_ALLOWED", 20)))
    ctx = derive_market_context(
        market_context
        or {
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
        }
    )
    mode = str(ctx.mode).upper()
    window_start = now_ts - window_sec

    allowed = 0
    candidates = 0
    decision_path = decision_events_path or _decision_events_path()
    for row in _iter_recent_rows(decision_path, window_start_epoch=window_start):
        if int(row.get("gatekeeper_allowed") or 0) != 1:
            continue
        allowed += 1
        if str(row.get("strategy_id") or "").strip():
            candidates += 1
    ratio = (float(candidates) / float(allowed)) if allowed > 0 else 0.0

    reason_counts: Counter[str] = Counter()
    rejects_path = reject_reasons_path or _reject_reasons_path()
    for row in _iter_recent_rows(rejects_path, window_start_epoch=window_start):
        reason = row.get("reason_code") or row.get("reason")
        if isinstance(reason, list):
            for value in reason:
                text = str(value or "").strip()
                if text:
                    reason_counts[text] += 1
            continue
        text = str(reason or "").strip()
        if text:
            reason_counts[text] += 1

    status = "OK"
    reason_codes: list[str] = []
    if mode in {"SIM", "PAPER", "OFFHOURS"}:
        if allowed >= min_allowed and ratio < min_ratio:
            status = "DEGRADED"
            reason_codes.append("SUGGESTION_RATIO_BELOW_FLOOR")
        elif allowed < min_allowed:
            status = "INSUFFICIENT_SAMPLE"
            reason_codes.append("SUGGESTION_SAMPLE_TOO_SMALL")
    payload = {
        "ts_epoch": now_ts,
        "ts_ist": now_ist().isoformat(),
        "status": status,
        "mode": mode,
        "market_open": bool(ctx.is_market_open),
        "window_sec": window_sec,
        "min_ratio": min_ratio,
        "min_allowed": min_allowed,
        "allowed_count": int(allowed),
        "candidate_count": int(candidates),
        "allowed_to_candidate_ratio": ratio,
        "reason_codes": reason_codes,
        "top_reject_reasons": dict(reason_counts.most_common(5)),
    }
    return payload


def persist_suggestion_reliability(payload: dict[str, Any]) -> None:
    events = _events_path()
    latest = _latest_path()
    events.parent.mkdir(parents=True, exist_ok=True)
    latest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")
    except Exception:
        pass
    try:
        latest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass
