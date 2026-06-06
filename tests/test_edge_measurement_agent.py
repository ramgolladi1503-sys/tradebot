from __future__ import annotations

from pathlib import Path

from core.agents.edge_measurement_agent import analyze_edge_measurement


def test_edge_measurement_agent_reports_offline_only_not_edge(tmp_path: Path):
    fixtures = Path("tests/fixtures/candidate_outcomes")
    report = analyze_edge_measurement(runtime_dir=tmp_path / ".runtime", logs_dir=tmp_path / "logs", offline_fixtures=fixtures)
    payload = report.to_dict()
    assert payload["verdict"] == "OFFLINE_ONLY_NOT_EDGE"
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
