"""Advisory-only market-event graph reversal strategy.

Implements the frozen discovered sequence:
    breadth_down_1:HIGH -> index_breadth_divergence:LOW -> breadth_down_1:LOW
    => BUY_CALL

The strategy is deliberately non-executable. It emits a raw candidate only when
three completed breadth-event snapshots are supplied through
``StrategyContext.metadata['market_event_graph_history']``. Missing, stale, or
malformed breadth evidence produces no candidate.
"""

from __future__ import annotations

from typing import Any

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement._utils import clamp_score, make_candidate, side_evidence

STRATEGY_ID = "market_event_graph_reversal_v1"
MOVEMENT_TYPE = "EXHAUSTION_REVERSAL"
FROZEN_GRAPH = (
    "breadth_down_1:HIGH",
    "index_breadth_divergence:LOW",
    "breadth_down_1:LOW",
)
MAX_EVENT_AGE_SEC = 420.0


def generate_market_event_graph_reversal_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Emit one advisory BUY_CALL candidate after the frozen three-event graph."""

    history = _history(ctx.metadata)
    if history is None:
        return ()

    labels = tuple(_label(row) for row in history[-3:])
    if labels != FROZEN_GRAPH:
        return ()

    if not _fresh(history[-1], ctx.ts_epoch):
        return ()

    side = side_evidence(ctx, "BUY_CALL")
    evidence = {
        "frozen_graph": list(FROZEN_GRAPH),
        "observed_graph": list(labels),
        "graph_source": "completed_constituent_breadth_events",
        "event_timestamps": [row.get("ts_epoch") for row in history[-3:]],
        "breadth_down_1_values": [row.get("breadth_down_1") for row in history[-3:]],
        "index_breadth_divergence_values": [
            row.get("index_breadth_divergence") for row in history[-3:]
        ],
        "research_entry_delay_bars": 1,
        "research_holding_bars": 15,
        "research_round_trip_cost_bps": 2,
        "research_validation_trades": 115,
        "research_validation_profit_factor": 2.4567905524,
        "research_holdout_trades": 25,
        "research_holdout_profit_factor": 4.1738554594,
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }

    candidate = make_candidate(
        ctx=ctx,
        regime=regime,
        strategy_id=STRATEGY_ID,
        movement_type=MOVEMENT_TYPE,
        direction="BUY_CALL",
        price_structure_score=clamp_score(0.72),
        side=side,
        entry_trigger="next_completed_bar_after_frozen_breadth_exhaustion_graph",
        invalid_if="breadth_selling_reexpands_before_entry_or_event_evidence_becomes_stale",
        rank_reason="broad selling expanded, index underperformed breadth, then selling participation contracted",
        evidence=evidence,
        warnings=(
            "RESEARCH_CANDIDATE_NOT_OPTION_VALIDATED",
            "SHADOW_ADVISORY_ONLY",
            "REQUIRES_ONE_BAR_DELAY",
        ),
        confluence_tags=(
            "constituent_breadth",
            "ordered_event_graph",
            "downside_exhaustion",
        ),
        suppression_tags=(
            "no_auto_execution",
            "no_same_bar_entry",
            "no_missing_breadth_fallback",
        ),
        strategy_version="v1",
        params_used={
            "FROZEN_GRAPH": list(FROZEN_GRAPH),
            "MAX_EVENT_AGE_SEC": MAX_EVENT_AGE_SEC,
            "ENTRY_DELAY_BARS": 1,
        },
        params_hash=None,
        promotion_state="ADVISORY_ONLY",
    )
    return (candidate,)


def _history(metadata: dict[str, Any]) -> list[dict[str, Any]] | None:
    raw = metadata.get("market_event_graph_history")
    if not isinstance(raw, (list, tuple)) or len(raw) < 3:
        return None
    rows = [row for row in raw if isinstance(row, dict)]
    if len(rows) < 3:
        return None
    return rows


def _label(row: dict[str, Any]) -> str:
    return str(row.get("event_label") or "").strip()


def _fresh(row: dict[str, Any], context_ts: float | None) -> bool:
    try:
        event_ts = float(row["ts_epoch"])
        now_ts = float(context_ts)
    except (KeyError, TypeError, ValueError):
        return False
    age = now_ts - event_ts
    return 0.0 <= age <= MAX_EVENT_AGE_SEC


__all__ = [
    "FROZEN_GRAPH",
    "MAX_EVENT_AGE_SEC",
    "MOVEMENT_TYPE",
    "STRATEGY_ID",
    "generate_market_event_graph_reversal_candidates",
]
