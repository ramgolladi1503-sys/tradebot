"""Phase2 adapter public module with real contract enforcement.

The implementation was moved behind this module so Phase2 CI compatibility
behavior can live in the owning adapter instead of import-time hooks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from config import config as cfg
from core import _engine_phase2_adapter_base as _phase2_base
from core._engine_phase2_adapter_base import *  # noqa: F401,F403

_base_build_candidates_phase2 = _phase2_base.build_candidates_phase2


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


def _phase2_contract_hard_drop(row: dict[str, Any]) -> bool:
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


def _phase2_contract_normal_ok(row: dict[str, Any]) -> bool:
    min_exec = float(_cfg("PHASE2_MIN_EXECUTION_SCORE", 0.0) or 0.0)
    min_liq = float(_cfg("PHASE2_MIN_LIQUIDITY_SCORE", 0.0) or 0.0)
    return bool(
        row.get("trade_id")
        and row.get("symbol")
        and not _phase2_contract_hard_drop(row)
        and row.get("execution_allowed", True)
        and row.get("tradable", True)
        and row.get("execution_ok", True)
        and (_sf(row.get("execution_score"), 1.0) or 0.0) >= min_exec
        and (_sf(row.get("liquidity_score"), 1.0) or 0.0) >= min_liq
        and _phase2_contract_spread_ok(row)
    )


def build_candidates_phase2(raw_candidates: list[Any] | None = None) -> list[dict[str, Any]]:  # noqa: F811
    """Build Phase2 candidates with formerly hooked Phase2 contracts inline."""
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

    out.sort(
        key=lambda row: (
            _sf(row.get("final_score", row.get("score", 0.0)), 0.0)
            if isinstance(row, dict)
            else 0.0
        ),
        reverse=True,
    )
    return out


_phase2_base.build_candidates_phase2 = build_candidates_phase2
_phase2_base._candidate_hour = _candidate_hour
_phase2_base._spread_pct = _spread_pct
_phase2_base._effective_max_spread_pct = _effective_max_spread_pct
run_engine_phase2 = _phase2_base.run_engine_phase2
