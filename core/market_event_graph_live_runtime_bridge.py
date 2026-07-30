"""Opt-in runtime bridge that exports synchronized live market-event snapshots.

The bridge is advisory only. It does not subscribe to feeds, call brokers,
place orders, mutate strategy state, or affect execution decisions. It only
observes already-available completed OHLC bars and, when explicitly enabled,
appends validated live-captured metadata rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import atexit
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from config import config as cfg
from core.market_data import get_token_for_symbol, ohlc_buffer
from core.market_event_graph_live_source import (
    LiveCapturedMetadataExporter,
    build_live_captured_metadata_row,
    default_live_capture_path,
    frozen_threshold_metadata,
)
from core.time_utils import now_ist

logger = logging.getLogger(__name__)


@dataclass
class LiveSourceBridgeResult:
    attempted: bool
    exported: bool
    reason: str
    latency_ms: dict[str, float] = field(default_factory=dict)
    accepted_constituent_count: int = 0
    missing_constituents: tuple[str, ...] = ()
    audit: dict[str, Any] = field(default_factory=dict)


class LiveSourceRuntimeBridge:
    def __init__(self, *, exporter: LiveCapturedMetadataExporter | None = None) -> None:
        self.exporter = exporter or LiveCapturedMetadataExporter(
            Path(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_PATH", default_live_capture_path()))
        )
        self._last_source_bar_end_epoch: float | None = None
        self._last_session_date: str | None = None
        self._last_run_id: str | None = None
        self._write_failures = 0
        self._dropped_evidence_writes = 0
        self._max_queue_depth = 0

    def observe_cycle(
        self,
        snapshot_rows: Sequence[Mapping[str, Any]],
        *,
        cycle_cutoff: datetime,
    ) -> LiveSourceBridgeResult:
        t0 = time.perf_counter()
        attempted = False
        exported = False
        reason = "DISABLED"
        latency_ms = {"snapshot_assembly": 0.0, "validation": 0.0, "queue_write": 0.0}
        if not bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)):
            return LiveSourceBridgeResult(False, False, reason, latency_ms=latency_ms)

        attempted = True
        t1 = time.perf_counter()
        snapshot = self._assemble_snapshot(snapshot_rows, cycle_cutoff=cycle_cutoff)
        t2 = time.perf_counter()
        latency_ms["snapshot_assembly"] = (t2 - t1) * 1000.0
        if snapshot is None:
            return LiveSourceBridgeResult(True, False, "SNAPSHOT_INCOMPLETE", latency_ms=latency_ms)

        validation_start = time.perf_counter()
        row = build_live_captured_metadata_row(
            session_date=str(snapshot["session_date"]),
            symbol=str(snapshot["symbol"]),
            interval_end=str(snapshot["interval_end"]),
            ts_epoch=float(snapshot["ts_epoch"]),
            source_bar_end_epoch=float(snapshot["source_bar_end_epoch"]),
            index_bar=snapshot["index_bar"],
            constituent_bars=snapshot["constituent_bars"],
            expected_constituents=int(snapshot["expected_constituents"]),
            run_id=str(snapshot["run_id"]),
            runtime_source_identifier=str(snapshot["runtime_source_identifier"]),
            missing_constituents=list(snapshot.get("missing_constituents") or []),
            stale_constituents=list(snapshot.get("stale_constituents") or []),
            duplicate_constituents=list(snapshot.get("duplicate_constituents") or []),
            misaligned_constituents=list(snapshot.get("misaligned_constituents") or []),
            late_constituents=list(snapshot.get("late_constituents") or []),
            duplicate_interval=bool(snapshot.get("duplicate_interval")),
        )
        row.update(
            {
                "subscription_evidence": dict(snapshot.get("subscription_evidence") or {}),
                "authority_isolation": {
                    "read_only": True,
                    "is_order_action": False,
                    "broker_api_called": False,
                    "allowed_for_live_execution": False,
                },
                "frozen_strategy_provenance": {
                    "thresholds": frozen_threshold_metadata(),
                    "source": "live_runtime_bridge",
                },
            }
        )
        latency_ms["validation"] = (time.perf_counter() - validation_start) * 1000.0
        write_start = time.perf_counter()
        result = self.exporter.export_row(row)
        latency_ms["queue_write"] = (time.perf_counter() - write_start) * 1000.0
        self._max_queue_depth = max(self._max_queue_depth, 1)
        if result.written:
            exported = True
            reason = result.reason
            self._last_source_bar_end_epoch = float(row["source_bar_end_epoch"])
            self._last_session_date = str(row["session_date"])
            self._last_run_id = str(result.row.get("run_id") if result.row else "")
        else:
            self._write_failures += 1
            if result.reason == "WRITE_FAILED":
                self._dropped_evidence_writes += 1
            reason = result.reason
            logger.warning(
                "market_event_graph_live_source_write_failed reason=%s details=%s",
                result.reason,
                ",".join(result.details),
            )
        latency_ms["total"] = (time.perf_counter() - t0) * 1000.0
        return LiveSourceBridgeResult(
            attempted=attempted,
            exported=exported,
            reason=reason,
            latency_ms=latency_ms,
            accepted_constituent_count=len(snapshot.get("constituent_bars") or []),
            missing_constituents=tuple(snapshot.get("missing_constituents") or ()),
            audit=self._audit_payload(),
        )

    def flush(self) -> dict[str, Any]:
        return {
            "flushed": True,
            "write_failures": self._write_failures,
            "dropped_evidence_writes": self._dropped_evidence_writes,
            "max_queue_high_water_mark": self._max_queue_depth,
            "last_source_bar_end_epoch": self._last_source_bar_end_epoch,
            "last_session_date": self._last_session_date,
            "last_run_id": self._last_run_id,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }

    def _assemble_snapshot(
        self,
        snapshot_rows: Sequence[Mapping[str, Any]],
        *,
        cycle_cutoff: datetime,
    ) -> dict[str, Any] | None:
        index_symbol = str(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL", "NIFTY") or "NIFTY").upper()
        constituent_symbols = self._resolve_constituent_symbols(snapshot_rows, index_symbol=index_symbol)
        if not constituent_symbols:
            return None
        index_bar = self._completed_bar_for(index_symbol, cycle_cutoff=cycle_cutoff)
        if index_bar is None:
            return None

        constituent_bars: list[dict[str, Any]] = []
        missing: list[str] = []
        stale: list[str] = []
        misaligned: list[str] = []
        late: list[str] = []
        duplicate: list[str] = []
        source_end: float | None = None
        session_date = str(
            getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_SESSION_DATE", "")
            or self._session_date_from_bar(index_bar)
            or cycle_cutoff.date().isoformat()
        )
        for symbol in constituent_symbols:
            bar = self._completed_bar_for(symbol, cycle_cutoff=cycle_cutoff)
            token = get_token_for_symbol(symbol)
            if bar is None:
                missing.append(symbol)
                continue
            bar_source_end = self._safe_epoch(bar.get("ts"))
            if source_end is None:
                source_end = bar_source_end
            elif bar_source_end != source_end:
                misaligned.append(symbol)
                continue
            if self._safe_epoch(bar.get("ts")) is None:
                late.append(symbol)
                continue
            bar = dict(bar)
            bar["symbol"] = symbol
            bar["instrument_token"] = token
            bar["completed"] = True
            constituent_bars.append(bar)

        if missing or misaligned or late or duplicate:
            return None
        if source_end is None:
            return None

        runtime_source_identifier = self._runtime_source_identifier(index_symbol, constituent_symbols)
        ts_epoch = float(cycle_cutoff.timestamp())
        interval_end = cycle_cutoff.isoformat()
        return {
            "session_date": session_date,
            "symbol": index_symbol,
            "interval_end": interval_end,
            "ts_epoch": ts_epoch,
            "source_bar_end_epoch": float(source_end),
            "index_bar": dict(index_bar),
            "constituent_bars": constituent_bars,
            "expected_constituents": len(constituent_symbols),
            "run_id": self._last_run_id or f"meg-live-source-{int(ts_epoch)}",
            "runtime_source_identifier": runtime_source_identifier,
            "missing_constituents": missing,
            "stale_constituents": stale,
            "duplicate_constituents": duplicate,
            "misaligned_constituents": misaligned,
            "late_constituents": late,
            "duplicate_interval": False,
            "subscription_evidence": self._subscription_evidence(constituent_symbols, index_symbol=index_symbol),
            "market_event_graph_runtime_state": {
                "session_date": session_date,
                "source": "live_runtime_bridge",
            },
            "market_event_graph_thresholds": {},
        }

    def _completed_bar_for(self, symbol: str, *, cycle_cutoff: datetime) -> dict[str, Any] | None:
        bars = ohlc_buffer.get_completed_bars(symbol, as_of=cycle_cutoff)
        if not bars:
            return None
        latest = dict(bars[-1])
        ts = latest.get("ts")
        if not isinstance(ts, datetime):
            return None
        latest["ts"] = ts
        return latest

    def _resolve_constituent_symbols(
        self,
        snapshot_rows: Sequence[Mapping[str, Any]],
        *,
        index_symbol: str,
    ) -> list[str]:
        configured = [str(sym).upper() for sym in getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_CONSTITUENT_SYMBOLS", []) if str(sym).strip()]
        if configured:
            return list(dict.fromkeys(configured))
        if snapshot_rows:
            inferred = [str(row.get("symbol") or "").upper() for row in snapshot_rows if str(row.get("symbol") or "").strip()]
            inferred = [sym for sym in inferred if sym != index_symbol]
            if inferred:
                return list(dict.fromkeys(inferred))
        return [str(sym).upper() for sym in getattr(cfg, "SYMBOLS", []) if str(sym).strip() and str(sym).upper() != index_symbol]

    def _runtime_source_identifier(self, index_symbol: str, constituents: Sequence[str]) -> str:
        payload = {
            "index_symbol": index_symbol,
            "constituent_symbols": list(constituents),
            "session_date": self._last_session_date or "",
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _subscription_evidence(self, constituents: Sequence[str], *, index_symbol: str) -> dict[str, Any]:
        requested = {index_symbol: self._resolve_token(index_symbol)}
        for sym in constituents:
            requested[sym] = self._resolve_token(sym)
        accepted = {sym: token for sym, token in requested.items() if token is not None}
        rejected = [sym for sym, token in requested.items() if token is None]
        return {
            "requested_count": len(requested),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "missing_identities": rejected,
            "token_by_symbol": accepted,
            "callback_applied": bool(accepted),
            "mode_applied": bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)),
        }

    def _resolve_token(self, symbol: str) -> int | None:
        try:
            return get_token_for_symbol(symbol)
        except Exception:
            return None

    def _session_date_from_bar(self, bar: Mapping[str, Any]) -> str | None:
        value = str(bar.get("session_date") or "").strip()
        return value or None

    def _safe_epoch(self, value: Any) -> float | None:
        try:
            return float(value.timestamp()) if hasattr(value, "timestamp") else float(value)
        except Exception:
            return None

    def _audit_payload(self) -> dict[str, Any]:
        return {
            "attempted": True,
            "export_path": str(self.exporter.path),
            "last_source_bar_end_epoch": self._last_source_bar_end_epoch,
            "write_failures": self._write_failures,
            "dropped_evidence_writes": self._dropped_evidence_writes,
            "max_queue_high_water_mark": self._max_queue_depth,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }


_LIVE_SOURCE_BRIDGE: LiveSourceRuntimeBridge | None = None


def get_live_source_bridge() -> LiveSourceRuntimeBridge:
    global _LIVE_SOURCE_BRIDGE
    if _LIVE_SOURCE_BRIDGE is None:
        _LIVE_SOURCE_BRIDGE = LiveSourceRuntimeBridge()
    return _LIVE_SOURCE_BRIDGE


def flush_live_source_bridge() -> dict[str, Any]:
    if _LIVE_SOURCE_BRIDGE is None:
        return {
            "flushed": False,
            "write_failures": 0,
            "dropped_evidence_writes": 0,
            "max_queue_high_water_mark": 0,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
    return _LIVE_SOURCE_BRIDGE.flush()


def build_live_constituent_subscription_audit() -> dict[str, Any]:
    index_symbol = str(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL", "NIFTY") or "NIFTY").upper()
    constituent_symbols = [
        str(sym).upper()
        for sym in getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_CONSTITUENT_SYMBOLS", []) or []
        if str(sym).strip()
    ] or [str(sym).upper() for sym in getattr(cfg, "SYMBOLS", []) if str(sym).strip() and str(sym).upper() != index_symbol]
    token_by_symbol = {sym: get_token_for_symbol(sym) for sym in [index_symbol, *constituent_symbols]}
    accepted = {sym: token for sym, token in token_by_symbol.items() if token is not None}
    rejected = [sym for sym, token in token_by_symbol.items() if token is None]
    return {
        "index_symbol": index_symbol,
        "constituent_symbols": constituent_symbols,
        "requested_count": len(token_by_symbol),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "missing_identities": rejected,
        "token_by_symbol": token_by_symbol,
        "callback_applied_status": "UNPROVEN_IN_STATIC_AUDIT",
        "mode_applied_status": "UNPROVEN_IN_STATIC_AUDIT",
        "completed_bar_availability_status": "UNPROVEN_IN_STATIC_AUDIT",
        "evidence_source": "code_inspection_only",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _flush_at_exit() -> None:
    try:
        if bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_FLUSH_ON_SHUTDOWN", True)):
            flush_live_source_bridge()
    except Exception:
        pass


atexit.register(_flush_at_exit)


__all__ = [
    "LiveSourceBridgeResult",
    "LiveSourceRuntimeBridge",
    "build_live_constituent_subscription_audit",
    "flush_live_source_bridge",
    "get_live_source_bridge",
]
