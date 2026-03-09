from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from config import config as cfg

from .events import EventStore
from .guard import DiskGuard
from .snapshots import SnapshotStore


@dataclass
class StorageRuntime:
    enabled: bool
    base_dir: Path
    guard: DiskGuard
    snapshots: SnapshotStore
    events: EventStore

    def emit_event(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return self.events.store_event(payload)

    def metrics(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "events_written_today": 0,
                "snapshots_written_today": 0,
                "disk_free_pct": 100.0,
                "storage_mode": "DISABLED",
            }
        event_metrics = self.events.metrics()
        snap_metrics = self.snapshots.metrics()
        return {
            "events_written_today": int(event_metrics.get("events_written_today", 0)),
            "snapshots_written_today": int(snap_metrics.get("snapshots_written_today", 0)),
            "disk_free_pct": float(event_metrics.get("disk_free_pct", 100.0)),
            "storage_mode": str(event_metrics.get("storage_mode", "NORMAL")),
        }


_RUNTIME: StorageRuntime | None = None


def _build_runtime() -> StorageRuntime:
    enabled = bool(getattr(cfg, "STORAGE_EVENTS_ENABLE", True))
    base_dir = Path(str(getattr(cfg, "STORAGE_BASE_DIR", "~/.trading_bot/data"))).expanduser()
    guard = DiskGuard(
        base_dir,
        min_free_pct=float(getattr(cfg, "STORAGE_MIN_FREE_PCT", 10.0)),
        critical_free_pct=float(getattr(cfg, "STORAGE_CRITICAL_FREE_PCT", 5.0)),
    )
    snapshots = SnapshotStore(base_dir, guard=guard)
    events = EventStore(base_dir, guard=guard, snapshot_store=snapshots)
    return StorageRuntime(
        enabled=enabled,
        base_dir=base_dir,
        guard=guard,
        snapshots=snapshots,
        events=events,
    )


def get_storage_runtime() -> StorageRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = _build_runtime()
    return _RUNTIME


def emit_event(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        return get_storage_runtime().emit_event(payload)
    except Exception:
        return None


def emit_gate_rejected_event(
    *,
    symbol: str | None,
    strategy: str | None,
    reason_code: str,
    mode: str | None,
    gate_name: str | None = None,
    data_source: str = "decision",
    missing_fields: list[str] | None = None,
    features_summary: Mapping[str, Any] | None = None,
    # ---- NEW (optional) structured decision diagnostics ----
    decision_stage: str | None = None,
    decision_explain: str | None = None,
    decision_blockers: list[str] | None = None,
    strategy_telemetry: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Emit a standardized gate_rejected event.

    Backwards compatible:
      - callers may continue to pass only the original parameters.
    New optional fields:
      - decision_stage / decision_explain / decision_blockers
      - strategy_telemetry (e.g. qual_fail_codes, picked_candidate)
    """
    sym = str(symbol or "").upper() or None
    mode_norm = str(mode or getattr(cfg, "TRADING_MODE", getattr(cfg, "EXECUTION_MODE", "PAPER"))).upper()

    # Ensure JSON-serializable + bounded
    blockers = [str(x) for x in (decision_blockers or []) if str(x).strip()]
    blockers = blockers[:64]
    telem = dict(strategy_telemetry or {})
    # Avoid huge payloads (candidate lists etc.)
    if isinstance(telem.get("qual_fail_reasons_raw"), list):
        telem["qual_fail_reasons_raw"] = list(telem.get("qual_fail_reasons_raw") or [])[:10]
    if isinstance(telem.get("all_candidates"), list):
        telem["all_candidates"] = list(telem.get("all_candidates") or [])[:10]

    payload = {
        "event_type": "gate_rejected",
        "desk": str(getattr(cfg, "DESK_ID", "DEFAULT")),
        "mode": mode_norm,
        "symbols": [sym] if sym else [],
        "gate_name": gate_name,
        "reason_code": str(reason_code or "")[:160],
        "data_source": str(data_source or "decision"),
        "missing_fields": list(missing_fields or []),
        "features_summary": dict(features_summary or {}),
        # ---- NEW fields (used by readiness_gate + dashboards) ----
        "decision_stage": str(decision_stage)[:120] if decision_stage else None,
        "decision_explain": str(decision_explain)[:500] if decision_explain else None,
        "decision_blockers": blockers,
        "strategy_telemetry": telem,
        "metadata": {"strategy": strategy},
    }
    return emit_event(payload)


def emit_candidate_created_event(
    *,
    symbol: str | None,
    strategy: str | None,
    mode: str | None,
    confidence: float | None,
    instrument: Mapping[str, Any] | None = None,
    features_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    instruments = [dict(instrument)] if isinstance(instrument, Mapping) else []
    payload = {
        "event_type": "candidate_created",
        "desk": str(getattr(cfg, "DESK_ID", "DEFAULT")),
        "mode": str(mode or getattr(cfg, "TRADING_MODE", getattr(cfg, "EXECUTION_MODE", "PAPER"))).upper(),
        "symbols": [str(symbol or "").upper()] if symbol else [],
        "confidence": confidence,
        "data_source": "decision",
        "missing_fields": [],
        "instruments": instruments,
        "features_summary": dict(features_summary or {}),
        "metadata": {"strategy": strategy},
    }
    return emit_event(payload)


def emit_trade_accepted_event(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    symbol = str(entry.get("symbol") or entry.get("underlying") or "").upper()
    instrument = {
        "symbol": symbol,
        "instrument_id": entry.get("instrument_id"),
        "instrument_token": entry.get("instrument_token"),
        "tradingsymbol": entry.get("tradingsymbol"),
    }
    payload = {
        "event_type": "trade_accepted",
        "desk": str(getattr(cfg, "DESK_ID", "DEFAULT")),
        "mode": str(getattr(cfg, "TRADING_MODE", getattr(cfg, "EXECUTION_MODE", "PAPER"))).upper(),
        "symbols": [symbol] if symbol else [],
        "reason_code": None,
        "confidence": entry.get("confidence"),
        "data_source": "trade_store",
        "latency_ms": entry.get("latency_ms"),
        "missing_fields": [],
        "instruments": [instrument],
        "features_summary": {
            "entry": entry.get("entry"),
            "stop_loss": entry.get("stop_loss"),
            "target": entry.get("target"),
            "qty": entry.get("qty"),
            "strategy": entry.get("strategy"),
        },
        "metadata": {
            "trade_id": entry.get("trade_id"),
            "side": entry.get("side"),
            "strategy": entry.get("strategy"),
        },
    }
    return emit_event(payload)


def emit_trade_exited_event(outcome: Mapping[str, Any]) -> dict[str, Any] | None:
    symbol = str(outcome.get("symbol") or "").upper()
    instrument = {
        "symbol": symbol,
        "instrument_id": outcome.get("instrument_id"),
        "instrument_token": outcome.get("instrument_token"),
        "tradingsymbol": outcome.get("tradingsymbol"),
    }
    payload = {
        "event_type": "trade_exited",
        "desk": str(getattr(cfg, "DESK_ID", "DEFAULT")),
        "mode": str(getattr(cfg, "TRADING_MODE", getattr(cfg, "EXECUTION_MODE", "PAPER"))).upper(),
        "symbols": [symbol] if symbol else [],
        "reason_code": outcome.get("exit_reason"),
        "confidence": None,
        "data_source": "trade_store",
        "missing_fields": [],
        "instruments": [instrument] if symbol else [],
        "features_summary": {
            "exit_price": outcome.get("exit_price"),
            "realized_pnl": outcome.get("realized_pnl"),
            "r_multiple_realized": outcome.get("r_multiple_realized"),
            "outcome_label": outcome.get("outcome_label"),
        },
        "metadata": {
            "trade_id": outcome.get("trade_id"),
            "exit_reason": outcome.get("exit_reason"),
        },
    }
    return emit_event(payload)


def emit_sla_violation_event(
    *,
    code: str,
    context: Mapping[str, Any] | None,
    severity: str | None,
) -> dict[str, Any] | None:
    context = dict(context or {})
    symbol = str(context.get("symbol") or "").upper()
    payload = {
        "event_type": "sla_violation",
        "desk": str(getattr(cfg, "DESK_ID", "DEFAULT")),
        "mode": str(getattr(cfg, "TRADING_MODE", getattr(cfg, "EXECUTION_MODE", "PAPER"))).upper(),
        "symbols": [symbol] if symbol else [],
        "reason_code": str(code or "")[:160],
        "data_source": "incident",
        "missing_fields": list(context.get("missing_fields") or []),
        "features_summary": {
            "severity": severity,
            "ltp": context.get("ltp"),
            "ltp_source": context.get("ltp_source"),
        },
        "metadata": context,
    }
    return emit_event(payload)


def storage_metrics() -> dict[str, Any]:
    try:
        return get_storage_runtime().metrics()
    except Exception:
        return {
            "events_written_today": 0,
            "snapshots_written_today": 0,
            "disk_free_pct": 100.0,
            "storage_mode": "ERROR",
        }
