from __future__ import annotations


def _install_execution_first_scoring_wrapper() -> None:
    """Install EDGE-34 execution-first scoring without rewriting trade_scoring.py.

    The project imports `compute_final_score` from `core.trade_scoring` in many
    places. This wrapper preserves the existing scoring contract, then applies a
    deterministic execution-first cap/penalty to executable candidates so high
    signal cannot hide weak tradability.
    """
    try:
        from core import trade_scoring as _trade_scoring
        from core.execution_first_scoring import apply_execution_first_score
    except Exception:
        return

    original = getattr(_trade_scoring, "_edge34_original_compute_final_score", None)
    if original is None:
        original = getattr(_trade_scoring, "compute_final_score", None)
        if original is None:
            return
        try:
            setattr(_trade_scoring, "_edge34_original_compute_final_score", original)
        except Exception:
            return

    def compute_final_score_execution_first(candidate, *args, **kwargs):
        result = dict(original(candidate, *args, **kwargs) or {})
        candidate_class = str(kwargs.get("candidate_class") or result.get("candidate_class") or "").strip().upper()
        priority_score = float(result.get("priority_score") or result.get("final_score") or 0.0)
        signal_score = float(result.get("signal_score") or 0.0)
        execution_score = float(result.get("execution_score") or 0.0)
        execution_ok = bool(
            (candidate.get("execution_ok") if isinstance(candidate, dict) else getattr(candidate, "execution_ok", True))
        )
        decision = apply_execution_first_score(
            priority_score=priority_score,
            signal_score=signal_score,
            execution_score=execution_score,
            candidate_class=candidate_class,
            execution_ok=execution_ok,
            stale_quote=bool(kwargs.get("stale_quote", False)),
            missing_liquidity=bool(kwargs.get("missing_liquidity", False)),
            spread_uncertain=bool(kwargs.get("spread_uncertain", False)),
            data_confidence=kwargs.get("data_confidence"),
        )
        adjusted_priority = float(decision.adjusted_score)
        class_cap = float(result.get("class_cap") or 1.0)
        adjusted_final = min(adjusted_priority, class_cap)
        result.update(
            {
                "priority_score": round(adjusted_priority, 6),
                "pre_cap_score": round(adjusted_priority, 6),
                "final_score": round(float(adjusted_final), 6),
                "execution_first_applied": bool(decision.reasons),
                "execution_first_cap_applied": decision.cap_applied,
                "execution_first_penalty_applied": decision.penalty_applied,
                "execution_first_reasons": list(decision.reasons),
                "execution_first_context": dict(decision.context or {}),
            }
        )
        return result

    try:
        setattr(_trade_scoring, "compute_final_score", compute_final_score_execution_first)
    except Exception:
        return


_install_execution_first_scoring_wrapper()
