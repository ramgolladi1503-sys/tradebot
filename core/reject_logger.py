from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Any

from config import config as cfg
from core.paths import logs_dir
from core.time_utils import now_ist, now_utc_epoch


def _compact_strategy_telemetry(raw: Any) -> dict | None:
    """
    Keep gate_rejected payloads small + stable.
    Accepts either a dict already, or returns None.
    """
    if not isinstance(raw, dict):
        return None

    keep_keys = (
        "qual_fail_codes",
        "picked_candidate",
        "precondition_failures",
        "qual_fail_reasons_raw",
    )
    out: dict[str, Any] = {}
    for key in keep_keys:
        if key in raw:
            out[key] = raw.get(key)

    ac = raw.get("all_candidates")
    if isinstance(ac, list) and len(ac) <= 10:
        out["all_candidates"] = ac

    return out or None


def _extract_strategy_telemetry(payload_extra: dict) -> dict | None:
    """
    Support multiple shapes so callers don't have to be perfect.
    Priority:
      1) extra["strategy_telemetry"]
      2) extra["facts"]["strategy_telemetry"]
      3) extra["strategy_telemetry_raw"] (fallback if you ever used that name)
    """
    if not isinstance(payload_extra, dict):
        return None

    direct = payload_extra.get("strategy_telemetry")
    if isinstance(direct, dict):
        return _compact_strategy_telemetry(direct)

    facts = payload_extra.get("facts")
    if isinstance(facts, dict) and isinstance(facts.get("strategy_telemetry"), dict):
        return _compact_strategy_telemetry(facts.get("strategy_telemetry"))

    raw = payload_extra.get("strategy_telemetry_raw")
    if isinstance(raw, dict):
        return _compact_strategy_telemetry(raw)

    return None


def _reject_log_path() -> Path:
    return Path(getattr(cfg, "REJECT_REASONS_LOG_PATH", str(logs_dir() / "reject_reasons.jsonl")))


def append_reject_reasons(
    *,
    symbol: str | None,
    strategy: str | None,
    reasons: Iterable[str] | None,
    mode: str | None,
    source: str = "decision",
    extra: dict | None = None,
) -> None:
    rows: list[str] = []
    seen = set()
    for raw_reason in (reasons or []):
        if raw_reason is None:
            continue
        reason = str(raw_reason).strip()
        if (not reason) or (reason.lower() == "none"):
            continue
        key = reason.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(reason)

    if not rows:
        return

    ts_epoch = now_utc_epoch()
    ts_ist = now_ist().isoformat()
    payload_extra = dict(extra or {})
    path = _reject_log_path()

    # 1) Write human-readable reject reasons log
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for reason in rows:
                rec = {
                    "ts_epoch": ts_epoch,
                    "ts_ist": ts_ist,
                    "symbol": str(symbol or "").upper() or "UNKNOWN",
                    "strategy": str(strategy or "UNKNOWN"),
                    "reason": reason,
                    "reason_code": reason,
                    "mode": str(mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                    "source": str(source),
                    "details": payload_extra,
                }
                handle.write(json.dumps(rec, ensure_ascii=True) + "\n")
    except Exception:
        pass

    # 2) Emit structured storage events (gate_rejected)
    try:
        from core.storage import emit_gate_rejected_event

        missing_fields = payload_extra.get("missing_fields") if isinstance(payload_extra.get("missing_fields"), list) else []
        gate_name = payload_extra.get("gate_name") if payload_extra.get("gate_name") is not None else source

        # NEW: pull structured decision diagnostics if present
        decision_stage = payload_extra.get("decision_stage") or payload_extra.get("stage")
        decision_explain = payload_extra.get("decision_explain") or payload_extra.get("explain")
        # Hardened: accept multiple shapes + compact for payload size
        strategy_telemetry = _extract_strategy_telemetry(payload_extra)

        # A stable, machine-friendly “blockers” list.
        # If caller provided a blockers list, prefer it; else use reasons we just normalized.
        decision_blockers = payload_extra.get("decision_blockers")
        if not isinstance(decision_blockers, list):
            decision_blockers = list(rows)

        for reason in rows:
            if bool(getattr(cfg, "GATE_REJECT_TRACE_ENABLE", True)):
                print(
                    "GATE_REJECT_EMIT",
                    {
                        "symbol": str(symbol or "").upper() or None,
                        "reason": str(reason),
                        "stage": str(decision_stage) if decision_stage is not None else None,
                        "blockers": [str(x) for x in (decision_blockers or []) if str(x).strip()],
                        "category": payload_extra.get("category"),
                        "trade_id": payload_extra.get("trade_id"),
                    },
                )
            emit_gate_rejected_event(
                symbol=str(symbol or "").upper() or None,
                strategy=str(strategy or "") or None,
                reason_code=str(reason),
                mode=str(mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                gate_name=str(gate_name) if gate_name is not None else None,
                data_source=str(source),
                missing_fields=[str(x) for x in missing_fields if str(x).strip()],
                features_summary=payload_extra,
                # ---- NEW structured fields ----
                decision_stage=str(decision_stage) if decision_stage is not None else None,
                decision_explain=str(decision_explain) if decision_explain is not None else None,
                decision_blockers=[str(x) for x in (decision_blockers or []) if str(x).strip()],
                strategy_telemetry=strategy_telemetry,
            )
    except Exception:
        pass
