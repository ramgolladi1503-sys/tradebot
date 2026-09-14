"""Strategy Decay Watchdog driven exclusively by Trade Truth records.

Monitors edge decay, hit rate degradation, and rejection drift across regimes.
Emits non-autonomous governance recommendations:
- KEEP_ACTIVE
- WATCH
- DEGRADED
- SHADOW
- DISABLE_PENDING_REVIEW

Invariant: Must never automatically grant trading authority or modify orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class DecayEvaluation:
    strategy_id: str
    total_decisions: int
    accepted_count: int
    rejected_count: int
    hit_rate: float | None
    mfe_mean: float | None
    mae_mean: float | None
    edge_ratio: float | None  # MFE / MAE
    status: str  # NORMAL, WATCH, DEGRADED, EDGE_DECAY_SUSPECTED, INSUFFICIENT_EVIDENCE
    recommendation: str  # KEEP_ACTIVE, WATCH, SHADOW, DISABLE_PENDING_REVIEW
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "total_decisions": self.total_decisions,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "hit_rate": self.hit_rate,
            "mfe_mean": self.mfe_mean,
            "mae_mean": self.mae_mean,
            "edge_ratio": self.edge_ratio,
            "status": self.status,
            "recommendation": self.recommendation,
            "evidence": self.evidence,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
        }


def evaluate_strategy_decay(
    records: Iterable[Mapping[str, Any]],
    *,
    min_samples: int = 5,
    min_edge_ratio: float = 1.0,
) -> dict[str, DecayEvaluation]:
    """Evaluate strategy decay from an iterable of truth records."""
    by_strategy: dict[str, list[Mapping[str, Any]]] = {}
    for r in records:
        strat = str(r.get("identity", {}).get("strategy_id") or "UNKNOWN")
        by_strategy.setdefault(strat, []).append(r)

    evaluations: dict[str, DecayEvaluation] = {}

    for strat, recs in by_strategy.items():
        total = len(recs)
        accepted = sum(
            1 for r in recs if r.get("decision", {}).get("governance_decision") == "ALLOWED"
        )
        rejected = total - accepted

        # Extract outcomes
        mfes = []
        maes = []
        hits = 0
        observed_outcomes = 0

        for r in recs:
            out = r.get("outcome") or {}
            mfe = out.get("mfe_abs")
            mae = out.get("mae_abs")
            realized = out.get("realized_outcome")

            if mfe is not None:
                mfes.append(float(mfe))
            if mae is not None:
                maes.append(float(mae))
            if realized in {"TARGET_HIT", "STOP_HIT"}:
                observed_outcomes += 1
                if realized == "TARGET_HIT":
                    hits += 1

        hit_rate = (hits / observed_outcomes) if observed_outcomes > 0 else None
        mfe_mean = (sum(mfes) / len(mfes)) if mfes else None
        mae_mean = (sum(maes) / len(maes)) if maes else None
        edge_ratio = (mfe_mean / mae_mean) if (mfe_mean and mae_mean and mae_mean > 0) else None

        # Determine Decay Status
        if total < min_samples:
            status = "INSUFFICIENT_EVIDENCE"
            recommendation = "WATCH"
        elif edge_ratio is not None and edge_ratio < 0.8:
            status = "EDGE_DECAY_SUSPECTED"
            recommendation = "DISABLE_PENDING_REVIEW"
        elif edge_ratio is not None and edge_ratio < min_edge_ratio:
            status = "DEGRADED"
            recommendation = "SHADOW"
        elif hit_rate is not None and hit_rate < 0.4:
            status = "WATCH"
            recommendation = "REDUCE_AUTHORITY"
        else:
            status = "NORMAL"
            recommendation = "KEEP_ACTIVE"

        evaluations[strat] = DecayEvaluation(
            strategy_id=strat,
            total_decisions=total,
            accepted_count=accepted,
            rejected_count=rejected,
            hit_rate=hit_rate,
            mfe_mean=mfe_mean,
            mae_mean=mae_mean,
            edge_ratio=edge_ratio,
            status=status,
            recommendation=recommendation,
            evidence={
                "sample_size": total,
                "observed_outcomes": observed_outcomes,
                "mfe_samples": len(mfes),
            },
        )

    return evaluations
