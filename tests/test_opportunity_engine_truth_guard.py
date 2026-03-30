from core.opportunity_engine import (
    _is_advisory_opportunity,
    _is_executable_opportunity,
    annotate_ranked_opportunities,
    select_top_opportunities,
)


def _candidate(**overrides):
    base = {
        "trade_id": "t1",
        "symbol": "NIFTY",
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "display_entry": 100.0,
        "display_entry_status": "displayable",
        "builder_confidence": 0.82,
        "permission_confidence": 0.82,
        "gating_final_confidence": 0.82,
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_real_executable_candidate_stays_executable():
    candidate = _candidate(trade_id="exec-real")
    assert _is_executable_opportunity(candidate) is True
    ranked = annotate_ranked_opportunities([candidate], scope="unit", top_n=1)
    assert ranked[0]["selected_for_execution"] is True
    assert ranked[0]["selection_reason"] == "selected_top_rank"


def test_fallback_candidate_never_becomes_executable():
    candidate = _candidate(
        trade_id="fallback-row",
        row_kind="recovered_fallback",
        source_flags={"candidate_origin": "fallback"},
    )
    assert _is_executable_opportunity(candidate) is False
    assert _is_advisory_opportunity(candidate) is True
    pools = select_top_opportunities([candidate], executable_top_n=3, advisory_top_n=3)
    assert pools["top_executable_opportunities"] == []
    assert len(pools["top_advisory_opportunities"]) == 1


def test_planning_only_candidate_is_blocked_even_with_execution_fields():
    candidate = _candidate(
        trade_id="planning-only",
        planning_only=True,
        source_flags={"candidate_origin": "planning_only"},
    )
    ranked = annotate_ranked_opportunities([candidate], scope="unit", top_n=1)
    assert ranked[0]["selected_for_execution"] is False
    assert ranked[0]["selection_reason"] == "execution_truth_blocked"
    assert ranked[0]["truth_allows_execution"] is False


def test_softened_candidate_stays_advisory_only():
    candidate = _candidate(
        trade_id="softened-row",
        row_kind="soft_reject",
        source_flags={"candidate_tags": ["softened"]},
    )
    assert _is_executable_opportunity(candidate) is False
    assert _is_advisory_opportunity(candidate) is True
