from __future__ import annotations

import json
from pathlib import Path

from research.opening_range_retest_edge_screen_v1 import contract as C
from research.opening_range_retest_edge_screen_v1 import controls
from research.opening_range_retest_edge_screen_v1.engine import measured_rows, metrics_payload, verify_source_authority


def test_contract_artifact_matches_code() -> None:
    path = Path("docs/agent_reviews/opening_range_retest_edge_screen_contract_v1.json")
    assert json.loads(path.read_text()) == C.contract_payload()
    assert path.with_suffix(path.suffix + ".sha256").read_text().split()[0] == C.sha256_file(str(path))


def test_source_authority_and_measured_counts() -> None:
    result = verify_source_authority(Path("docs/agent_reviews"))
    assert result["source_authority"]["failures"] == []
    ledger = result["ledger"]
    assert len(measured_rows(ledger, 15)) == 2155
    assert len(measured_rows(ledger, 30)) == 2086


def test_primary_metrics_are_session_equal() -> None:
    ledger = verify_source_authority(Path("docs/agent_reviews"))["ledger"]
    metrics = metrics_payload(ledger)
    assert metrics["primary"]["candidate_count"] == 2155
    assert metrics["primary"]["session_count"] > 0
    assert "session_cluster_bootstrap" in metrics["primary"]


def test_control_cases_cover_required_minimum() -> None:
    assert len(controls.CONTROL_CASES) >= 50
    failed = [case for case in controls.CONTROL_CASES if not controls.run_control_case(case[0])["passed"]]
    assert failed == []

