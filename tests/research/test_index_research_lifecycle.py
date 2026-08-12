from research.governance.index_research_contract import DiscoveryResult, ResearchOutcome
from research.governance.index_research_lifecycle import certify_offline, freeze_model


def test_blocked_data_stays_blocked_through_freeze_and_certification():
    decision = freeze_model(DiscoveryResult("BANKNIFTY", ResearchOutcome.BLOCKED_DATA))
    assert decision.status == "BLOCKED_DATA"
    assert certify_offline(decision) == "BLOCKED_DATA"


def test_no_edge_is_honest_terminal_without_model_sha():
    result = DiscoveryResult("SENSEX", ResearchOutcome.NO_STRUCTURAL_EDGE_FOUND, evidence_sha256="e" * 64)
    decision = freeze_model(result)
    assert decision.model_sha256 is None
    assert certify_offline(decision) == "NO_STRUCTURAL_EDGE_FOUND"
