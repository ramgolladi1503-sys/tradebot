from types import SimpleNamespace

from core.candidate_soft_reject import apply_latency_penalty


def test_latency_soften_preserves_strategy_family():
    candidate = {
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "candidate_type": "directional",
        "option_type": "PE",
        "direction": "BUY_PUT",
        "rank_score": 0.6,
        "confidence": 0.55,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "execution_allowed": True,
    }

    softened = apply_latency_penalty(candidate, latency_action="halt_all", execution_mode="SIM")

    assert softened["strategy_family"] == "breakout"
    assert softened.get("strategy_family") != "latency_guard"
    assert softened.get("option_type") == "PE"
    assert softened.get("execution_status") == "queue_only"
    assert softened.get("execution_allowed") is False
    assert softened.get("permission") == "QUEUE_ONLY"
    assert softened.get("final_action") == "QUEUE_ONLY"
    assert softened.get("candidate_status") == "near_executable"
    assert softened.get("rank_score") is not None
    assert softened.get("rank_score") < candidate["rank_score"]


def test_latency_soften_infers_option_type_and_direction():
    candidate = {
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "candidate_type": "directional",
        "direction": "BUY_PUT",
        "rank_score": 0.5,
        "confidence": 0.4,
    }

    softened = apply_latency_penalty(candidate, latency_action="halt_all", execution_mode="SIM")

    assert softened.get("option_type") == "PE"
    assert softened.get("direction") == "BUY_PUT"


def test_latency_soften_preserves_namespace_candidates():
    candidate = SimpleNamespace(
        trade_id="NIFTY-1",
        symbol="NIFTY",
        strategy_family="breakout",
        candidate_status="executable",
        candidate_type="directional",
        option_type="PE",
        direction="BUY_PUT",
        rank_score=0.6,
        confidence=0.55,
        permission="EXECUTE",
        final_action="EXECUTE",
        execution_status="executable",
        execution_allowed=True,
    )

    softened = apply_latency_penalty(candidate, latency_action="cooldown", execution_mode="LIVE")

    assert softened["trade_id"] == "NIFTY-1"
    assert softened["symbol"] == "NIFTY"
    assert softened["strategy_family"] == "breakout"
    assert softened["candidate_status"] == "near_executable"
    assert softened["execution_status"] == "queue_only"
    assert softened["execution_allowed"] is False
    assert softened["permission"] == "QUEUE_ONLY"
    assert softened["final_action"] == "QUEUE_ONLY"
    assert softened["rank_score"] is not None
