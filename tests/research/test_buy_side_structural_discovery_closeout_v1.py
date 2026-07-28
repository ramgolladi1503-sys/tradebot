import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/close_buy_side_structural_discovery_campaign_v1.py"


def read(path: Path):
    return json.loads(path.read_text())


def generate(path: Path) -> None:
    subprocess.run(
        ["python3", str(SCRIPT), "--output-dir", str(path)],
        cwd=ROOT,
        check=True,
    )


def test_closeout_preserves_evidence_and_fail_closed_recommendation(tmp_path):
    out = tmp_path / "closeout"
    generate(out)
    ledger = read(out / "campaign_evidence_ledger.json")
    rows = {row["canonical_mechanism_name"]: row for row in ledger["mechanisms"]}
    required = {
        "bullish_ORB", "bearish_ORB", "underlying_percentage_momentum",
        "ORB_plus_momentum_agreement", "opening_state_momentum_variants",
        "mean_reversion_variants", "delayed_option_convexity_after_underlying_confirmation",
        "premium_compression_release_with_underlying_state_filter", "FQSDV2_PAIR_ASYM_01",
        "FQSDV2_LADDER_CONFIRM_02", "FQSDV2_EXPIRY_TRANSITION_03",
        "broad_joint_state_partition_candidates",
    }
    assert required <= rows.keys()
    assert rows["FQSDV2_PAIR_ASYM_01"]["gross_expectancy_points"] < 0
    assert rows["FQSDV2_LADDER_CONFIRM_02"]["gross_expectancy_points"] < 0
    assert rows["FQSDV2_EXPIRY_TRANSITION_03"]["gross_expectancy_points"] < 0
    assert rows["premium_compression_release_with_underlying_state_filter"]["final_status"] == "UNRESOLVED_UNDERPOWERED"
    recommendation = read(out / "operational_recommendation.json")
    assert recommendation["recommendation"] == "NO_STRATEGY_ACTIVATION"
    assert recommendation["allowed_for_live_execution"] is False
    assert recommendation["broker_api_called"] is False


def test_superseded_evidence_and_reopen_policy_are_explicit(tmp_path):
    out = tmp_path / "closeout"
    generate(out)
    mapping = read(out / "superseded_evidence_map.json")["mappings"]
    assert any(row["status"] == "SUPERSEDED_BY_VALID_RERUN" and row["citation_rule"] == "MUST_NEVER_BE_CITED_AS_FINAL" for row in mapping)
    reopen = read(out / "reopen_conditions.json")
    history = next(row for row in reopen["conditions"] if row["id"] == "LONGER_INDEPENDENT_HISTORY")
    assert history["minimum"] == {
        "additional_independent_sessions": 24,
        "additional_independent_expiries": 18,
        "premium_compression_frozen_events": 63,
    }
    assert "threshold grids" in reopen["never_sufficient_alone"]
    assert "renamed or lightly modified rejected mechanisms" in reopen["never_sufficient_alone"]


def test_registry_and_two_directory_generation_are_deterministic(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate(first)
    generate(second)
    a = read(first / "determinism_report.json")
    b = read(second / "determinism_report.json")
    assert a["semantic_hashes"] == b["semantic_hashes"]
    assert a["status"] == "PASS"
    registry = read(first / "mechanism_status_registry.json")
    assert all(row["mechanism_fingerprint"] and row["economic_family_fingerprint"] for row in registry["registry"])
    audit = read(first / "independent_audit.json")
    verdict = read(first / "final_verdict.json")
    assert audit["status"] == "PASS"
    assert verdict["final_verdict"] == "BUY_SIDE_DISCOVERY_CAMPAIGN_CLOSED"
    assert verdict["new_strategy_discovered"] is False
