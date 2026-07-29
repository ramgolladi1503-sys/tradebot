from pathlib import Path

from scripts.audit_late_day_ce_inventory_rebound_v10_causality import audit


def test_v10_detects_future_entry_price_membership_leak() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = audit(root)
    assert payload["principal_verdict"] == "INVALID_FUTURE_ENTRY_PRICE_SIGNAL_MEMBERSHIP_LEAK"
    assert payload["current_structural_edge_claim_valid"] is False
    assert "NEXT_BAR_ENTRY_PRICE_USED_AS_SIGNAL_ELIGIBILITY_FILTER" in payload["defects"]
    assert "NEXT_BAR_ENTRY_PRICE_USED_TO_RANK_SIMULTANEOUS_CANDIDATES" in payload["defects"]
    assert payload["paper_or_live_authorized"] is False
    assert payload["allowed_for_live_execution"] is False
