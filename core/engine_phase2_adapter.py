"""Phase2 adapter public module with real contract enforcement.

The implementation was moved behind this module so Phase2 CI compatibility
behavior can live in the owning adapter instead of import-time hooks.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from config import config as cfg
from core import _engine_phase2_adapter_base as _phase2_base
from core._engine_phase2_adapter_base import *  # noqa: F401,F403
from core.paths import logs_dir
from core.feed.artifact_loader import load_current_feed_runtime
from core.runtime_phase2_rejection_evidence import (
    build_phase2_rejection_evidence_payload,
    write_phase2_rejection_evidence_latest,
)
from core.runtime_feed_truth_snapshot import build_feed_truth_snapshot, write_feed_truth_snapshot_latest

_base_build_candidates_phase2 = _phase2_base.build_candidates_phase2
# Guard against module reload / re-import recursion: this adapter assigns its
# wrapper back onto the base module. If imported again, the "base" callable may
# already be the wrapper. Delegate through the stable base reference instead.
if bool(getattr(_base_build_candidates_phase2, "_ci_phase2_contract_patch", False)):
    _base_build_candidates_phase2 = getattr(_phase2_base, "_BASE_BUILD_CANDIDATES_PHASE2", _base_build_candidates_phase2)

CONTRACT_FALLBACK_BLOCKER = "CONTRACT_RESOLUTION_FALLBACK_BLOCKED"
CONTRACT_FALLBACK_REASON = "contract_resolution_fallback_blocked"

_CONTRACT_FALLBACK_BOOL_KEYS = {
    "contract_resolution_fallback",
    "contract_resolution_fallback_used",
    "contract_resolution_fallback_blocked",
    "fallback_contract_resolution",
    "fallback_contract_resolution_used",
    "contract_fallback_used",
    "fallback_resolved_contract",
    "fallback_contract",
    "is_fallback_contract",
    "option_contract_fallback",
    "contract_resolution_is_fallback",
}

_CONTRACT_FALLBACK_TEXT_KEYS = {
    "contract_resolution_mode",
    "contract_resolution_status",
    "contract_resolution_source",
    "contract_resolution_reason",
    "contract_resolution_event",
    "contract_source",
    "resolution_source",
    "resolution_mode",
    "resolution_status",
    "option_resolution_source",
    "execution_block_reason",
    "order_policy_reason",
}

_CONTRACT_FALLBACK_MARKERS = {
    "CONTRACT_RESOLUTION_FALLBACK",
    "CONTRACT_RESOLUTION_FALLBACK_BLOCKED",
    "FALLBACK_CONTRACT_RESOLUTION",
    "FALLBACK_CONTRACT",
    "CONTRACT_FALLBACK",
}


def _sf(value: Any, default: float | None = 0.0) -> float | None:
    try:
        out = float(value)
        return default if out != out else out
    except Exception:
        return default


def _cfg(name: str, default: Any = None) -> Any:
    try:
        if hasattr(cfg, name):
            return getattr(cfg, name)
    except Exception:
        pass
    return default


def _has_candidate_timestamp(candidate: dict[str, Any]) -> bool:
    return any(key in candidate for key in ("timestamp_epoch", "decision_ts_epoch", "ts_epoch"))


def _candidate_hour(candidate: dict[str, Any]) -> int:  # noqa: F811
    """Return the candidate hour, defaulting missing timestamps to in-hours.

    Tests monkeypatch this symbol directly. When no timestamp is present and no
    monkeypatch is active, Phase2 treats the row as in-hours instead of using
    the test runner's wall-clock time.
    """
    epoch = (
        _sf(candidate.get("timestamp_epoch"), None)
        or _sf(candidate.get("decision_ts_epoch"), None)
        or _sf(candidate.get("ts_epoch"), None)
    )
    if epoch is not None and epoch > 0:
        try:
            return int(datetime.fromtimestamp(float(epoch)).hour)
        except Exception:
            pass
    return int(_cfg("PHASE2_MARKET_START_HOUR", 9) or 9)


def _spread_pct(candidate: dict[str, Any]) -> float | None:  # noqa: F811
    spread_pct = _sf(candidate.get("spread_pct"), None)
    if spread_pct is not None:
        return max(0.0, float(spread_pct))
    bid = _sf(candidate.get("best_bid") or candidate.get("bid"), None)
    ask = _sf(candidate.get("best_ask") or candidate.get("ask"), None)
    ltp = _sf(
        candidate.get("opt_ltp")
        or candidate.get("current_ltp")
        or candidate.get("ltp"),
        None,
    )
    if bid is None or ask is None or ltp in (None, 0.0):
        return None
    return max(0.0, float(ask - bid) / max(float(ltp), 1e-9))


def _effective_max_spread_pct(candidate: dict[str, Any]) -> float:  # noqa: F811
    base_spread = float(
        _cfg("PHASE2_MAX_SPREAD_PCT", _cfg("MAX_SPREAD_PCT", 0.02))
        or _cfg("MAX_SPREAD_PCT", 0.02)
        or 0.02
    )
    high_vol_spread = float(
        _cfg("PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base_spread) or base_spread
    )
    vol_cutoff = float(_cfg("PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
    volatility = max(
        float(_sf(candidate.get("volatility"), 0.0) or 0.0),
        float(_sf(candidate.get("volatility_score"), 0.0) or 0.0),
        float(_sf(candidate.get("vol_z"), 0.0) or 0.0),
    )
    max_spread = high_vol_spread if volatility >= vol_cutoff else base_spread
    start = int(_cfg("PHASE2_MARKET_START_HOUR", 9) or 9)
    end = int(_cfg("PHASE2_MARKET_END_HOUR", 15) or 15)
    mult = float(_cfg("PHASE2_SPREAD_OFFHOURS_MULT", 1.0) or 1.0)
    hour = int(_candidate_hour(candidate))
    if not (start <= hour < end):
        max_spread *= mult
    return max(float(max_spread), 1e-6)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", "none", ""}:
        return False
    return False


def _iter_contract_resolution_contexts(row: dict[str, Any]):
    yield row
    for key in (
        "source_flags",
        "contract_resolution",
        "option_contract_resolution",
        "resolved_contract",
        "option_contract",
        "selected_contract",
        "instrument_resolution",
        "resolution",
    ):
        value = row.get(key)
        if isinstance(value, dict):
            yield value


def _iter_reason_texts(row: dict[str, Any]):
    for ctx in _iter_contract_resolution_contexts(row):
        for key in _CONTRACT_FALLBACK_TEXT_KEYS:
            value = ctx.get(key)
            if value not in (None, ""):
                yield str(value)
        for key in (
            "reason",
            "reasons",
            "blocker",
            "blockers",
            "hard_blockers",
            "execution_blockers",
            "gate_reasons",
            "penalty_reasons",
            "confidence_penalty_reasons",
            "event",
            "events",
        ):
            value = ctx.get(key)
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    if item not in (None, ""):
                        yield str(item)
            elif value not in (None, ""):
                yield str(value)


def _is_contract_resolution_fallback(row: dict[str, Any]) -> bool:
    """Return true when candidate carries fallback contract-resolution evidence.

    This intentionally targets contract-resolution fallback, not every generic
    advisory/fallback candidate. A fallback-resolved instrument is unsafe for
    execution because the orderable contract mapping is uncertain.
    """

    for ctx in _iter_contract_resolution_contexts(row):
        for key in _CONTRACT_FALLBACK_BOOL_KEYS:
            if _as_bool(ctx.get(key)):
                return True
        for key in _CONTRACT_FALLBACK_TEXT_KEYS:
            text = str(ctx.get(key) or "").strip().upper()
            if text in _CONTRACT_FALLBACK_MARKERS or text == "FALLBACK":
                return True
            if "CONTRACT" in text and "FALLBACK" in text:
                return True
            if "RESOLUTION" in text and "FALLBACK" in text:
                return True

    for text in _iter_reason_texts(row):
        normalized = str(text or "").strip().upper()
        if normalized in _CONTRACT_FALLBACK_MARKERS:
            return True
        if "CONTRACT_RESOLUTION_FALLBACK" in normalized:
            return True
        if "FALLBACK_CONTRACT" in normalized:
            return True

    return False


def _append_unique(row: dict[str, Any], key: str, value: str) -> None:
    current = row.get(key)
    if isinstance(current, list):
        values = list(current)
    elif current in (None, ""):
        values = []
    else:
        values = [current]
    if value not in {str(item) for item in values}:
        values.append(value)
    row[key] = values


def _block_contract_resolution_fallback(row: dict[str, Any]) -> dict[str, Any]:
    """Force fallback-resolved contract candidates into non-executable shape."""

    row["execution_allowed"] = False
    row["tradable"] = False
    row["execution_ok"] = False
    row["truth_allows_execution"] = False
    row["execution_blocked"] = True
    row["permission"] = "QUEUE_ONLY"
    row["final_action"] = "QUEUE_ONLY"
    row["max_final_action"] = "QUEUE_ONLY"
    row["execution_status"] = "blocked"
    row["candidate_status"] = "blocked"
    row["execution_block_reason"] = CONTRACT_FALLBACK_REASON
    row["order_policy_reason"] = CONTRACT_FALLBACK_REASON
    row["contract_resolution_fallback_blocked"] = True
    _append_unique(row, "hard_blockers", CONTRACT_FALLBACK_BLOCKER)
    _append_unique(row, "blockers", CONTRACT_FALLBACK_BLOCKER)
    _append_unique(row, "gate_reasons", CONTRACT_FALLBACK_BLOCKER)
    source_flags = row.get("source_flags")
    if not isinstance(source_flags, dict):
        source_flags = {}
    source_flags["contract_resolution_fallback_blocked"] = True
    source_flags["order_policy_reason"] = CONTRACT_FALLBACK_REASON
    row["source_flags"] = source_flags
    return row


def _phase2_contract_hard_drop(row: dict[str, Any]) -> bool:
    if _is_contract_resolution_fallback(row):
        _block_contract_resolution_fallback(row)
        return True

    if bool(_cfg("PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
        candidate_origin = str(row.get("candidate_origin") or "").strip().lower()
        strategy_family = str(row.get("strategy_family") or "").strip().lower()
        penalties = row.get("penalty_reasons") or row.get("confidence_penalty_reasons")
        degraded = row.get("execution_context_degraded") or row.get("phase2_soft_degrade_reason")
        if (
            candidate_origin == "softened_builder_path"
            or strategy_family == "builder_soft_reject"
            or bool(penalties)
            or bool(degraded)
        ):
            return True

    if bool(_cfg("PHASE2_PLAYBOOK_SELECTION_ENABLE", False)):
        if not (
            row.get("playbook")
            or row.get("playbook_id")
            or row.get("selected_playbook")
            or row.get("phase2_playbook")
        ):
            return True

    blockers = {str(value).strip().upper() for value in list(row.get("hard_blockers") or [])}
    if "UNRESOLVED_CONTRACT" in blockers or "FEED_STALE" in blockers:
        return True

    bid = _sf(row.get("best_bid") or row.get("bid"), None)
    ask = _sf(row.get("best_ask") or row.get("ask"), None)
    ltp = _sf(row.get("current_ltp") or row.get("opt_ltp") or row.get("ltp"), None)
    if bid is not None and ask is not None and ltp is not None and ltp > 0:
        mid = (float(bid) + float(ask)) / 2.0
        if mid > 0 and abs(mid - float(ltp)) / max(float(ltp), 1e-9) > 0.25:
            return True
    return False


def _phase2_contract_spread_ok(row: dict[str, Any]) -> bool:
    spread = _spread_pct(row)
    if spread is None:
        return True
    return float(spread) <= float(_effective_max_spread_pct(row))


def _phase2_contract_has_fallback_or_advisory(row: dict[str, Any]) -> bool:
    return bool(
        row.get("fallback_used")
        or row.get("recovered_fallback")
        or str(row.get("quote_source") or "") == "recovered_fallback"
        or row.get("advisory_only")
        or row.get("phase2_quote_age_fallback_used")
        or row.get("phase2_spread_fallback_used")
        or row.get("phase2_liquidity_fallback_used")
        or row.get("contract_resolution_fallback_used")
        or row.get("contract_fallback_used")
    )


def _phase2_contract_normal_ok(row: dict[str, Any]) -> bool:
    min_exec = float(_cfg("PHASE2_MIN_EXECUTION_SCORE", 0.0) or 0.0)
    min_liq = float(_cfg("PHASE2_MIN_LIQUIDITY_SCORE", 0.0) or 0.0)
    
    if _phase2_contract_has_fallback_or_advisory(row):
        return False
        
    return bool(
        row.get("trade_id")
        and row.get("symbol")
        and not _phase2_contract_hard_drop(row)
        and row.get("execution_allowed", True)
        and row.get("tradable", True)
        and row.get("execution_ok") is True
        and (_sf(row.get("execution_score"), 1.0) or 0.0) >= min_exec
        and (_sf(row.get("liquidity_score"), 1.0) or 0.0) >= min_liq
        and _phase2_contract_spread_ok(row)
    )


def _finalize_phase2_output(rows: list[Any]) -> list[Any]:
    """Fail-closed final guard against fallback contract leakage.

    The adapter intentionally works with shallow copies for compatibility with
    legacy Phase2 behavior. This final pass prevents raw or copied fallback rows
    from leaking back into output after mutation/re-add paths.
    """

    safe_rows: list[Any] = []
    for row in rows:
        if isinstance(row, dict) and _is_contract_resolution_fallback(row):
            _block_contract_resolution_fallback(row)
            continue
        safe_rows.append(row)
    return safe_rows


def build_candidates_phase2(raw_candidates: list[Any] | None = None) -> list[dict[str, Any]]:  # noqa: F811
    """Build Phase2 candidates with formerly hooked Phase2 contracts inline."""
    feed_path = logs_dir() / "feed_runtime_latest.json"
    feed_ok = False
    tick_age = 0.0
    depth_age = 0.0
    loaded_runtime = load_current_feed_runtime(feed_path)
    if loaded_runtime.get("valid"):
        try:
            feed_payload = dict(loaded_runtime.get("payload") or {})
            feed_ok = bool(feed_payload.get("feed_ok"))
            tick_age = float(feed_payload.get("last_tick_age_sec") or 0.0)
            depth_age = float(feed_payload.get("last_depth_age_sec") or 0.0)
        except Exception:
            feed_ok = False

    if not feed_ok or tick_age > 2.5 or depth_age > 6.0:
        out = []
    else:
        raw = [dict(row) for row in list(raw_candidates or []) if isinstance(row, dict)]

        # Keep the private implementation aligned when it calls its own helpers.
        _phase2_base._candidate_hour = _candidate_hour
        _phase2_base._spread_pct = _spread_pct
        _phase2_base._effective_max_spread_pct = _effective_max_spread_pct

        current = [
            dict(row) if isinstance(row, dict) else row
            for row in list(_base_build_candidates_phase2(raw_candidates) or [])
        ]
        out = [
            row
            for row in current
            if not isinstance(row, dict)
            or (not _phase2_contract_hard_drop(row) and _phase2_contract_spread_ok(row))
        ]

        seen = {str(row.get("trade_id")) for row in out if isinstance(row, dict)}
        for row in raw:
            trade_id = str(row.get("trade_id") or "")
            if trade_id and trade_id not in seen and _phase2_contract_normal_ok(row):
                out.append(row)
                seen.add(trade_id)

        out = _finalize_phase2_output(out)
        out.sort(
            key=lambda row: (
                _sf(row.get("final_score", row.get("score", 0.0)), 0.0)
                if isinstance(row, dict)
                else 0.0
            ),
            reverse=True,
        )
    try:
        if bool(getattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True)):
            drop_counts = getattr(_phase2_base.build_candidates_phase2, "_last_drop_reason_counts", {}) or {}
            feed_truth_payload = {}
            try:
                feed_path = logs_dir() / "feed_truth_latest.json"
                if feed_path.exists():
                    feed_truth_payload = json.loads(feed_path.read_text(encoding="utf-8"))
            except Exception:
                feed_truth_payload = {}
            payload = build_phase2_rejection_evidence_payload(
                phase2_state=None,
                raw_candidates=[row for row in list(raw_candidates or []) if isinstance(row, dict)],
                ranked_candidates=[row for row in list(out or []) if isinstance(row, dict)],
                drop_reason_counts=drop_counts if isinstance(drop_counts, dict) else {},
                feed_truth=feed_truth_payload if isinstance(feed_truth_payload, dict) else {},
            )
            write_phase2_rejection_evidence_latest(payload=payload)
            try:
                feed_payload = {}
                feed_path = (logs_dir() / "feed_runtime_latest.json")
                if feed_path.exists():
                    feed_payload = json.loads(feed_path.read_text(encoding="utf-8"))
                truth_payload = build_feed_truth_snapshot(
                    feed_runtime=feed_payload if isinstance(feed_payload, dict) else {},
                    phase2_rejection=payload,
                )
                write_feed_truth_snapshot_latest(payload=truth_payload)
            except Exception:
                pass
    except Exception:
        pass
    return out


# The adapter now owns the Phase2 contract. Marking the callable prevents the
# CI compatibility shim from wrapping it and reintroducing fallback rows.
build_candidates_phase2._ci_phase2_contract_patch = True

_phase2_base.build_candidates_phase2 = build_candidates_phase2
_phase2_base._candidate_hour = _candidate_hour
_phase2_base._spread_pct = _spread_pct
_phase2_base._effective_max_spread_pct = _effective_max_spread_pct
run_engine_phase2 = _phase2_base.run_engine_phase2
