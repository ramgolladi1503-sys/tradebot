from __future__ import annotations

import json
from pathlib import Path

from scripts.run_architecture_hardening_campaign import run_campaign


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_campaign_consumes_repository_snapshot_corpus(tmp_path: Path) -> None:
    candidate = {
        "trade_id": "T1",
        "candidate_origin": "strategy",
        "execution_status": "EXECUTABLE",
        "execution_entry_status": "EXECUTABLE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "execution_entry": 101.5,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
    }
    _write(tmp_path / "artifacts" / "candidate_snapshot.jsonl", json.dumps(candidate) + "\n")
    _write(tmp_path / "core" / "orchestrator.py", "def run():\n    return None\n")
    _write(tmp_path / "strategies" / "trade_builder.py", "def build():\n    return None\n")
    _write(
        tmp_path / "core" / "runtime_snapshot_producer.py",
        "def build_ranked_opportunity_report():\n    return []\n\n"
        "def render():\n    ranked = build_ranked_opportunity_report()\n    return ranked\n",
    )
    _write(tmp_path / "core" / "ranking_orchestrator.py", "def rank_candidates(rows):\n    return rows\n")

    output = tmp_path / "evidence" / "campaign.json"
    payload = run_campaign(tmp_path, output)

    assert output.exists()
    assert payload["rows_scanned"] == 1
    assert payload["verdict"]["helper_parity"] is True
    assert payload["verdict"]["shadow_parity"] is True
    assert payload["verdict"]["ranking_execution_authority_proven"] is False


def test_campaign_reports_shadow_mismatch_without_hiding_it(tmp_path: Path) -> None:
    candidate = {
        "trade_id": "T2",
        "candidate_origin": "strategy",
        "execution_status": "EXECUTABLE",
        "execution_entry_status": "EXECUTABLE",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "execution_entry": 101.5,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "quote_validation_status": "UNTRUSTED",
    }
    _write(tmp_path / "logs" / "suggestions.jsonl", json.dumps(candidate) + "\n")
    _write(tmp_path / "core" / "orchestrator.py", "x = 1\n")
    _write(tmp_path / "strategies" / "trade_builder.py", "x = 1\n")
    _write(tmp_path / "core" / "runtime_snapshot_producer.py", "x = 1\n")
    _write(tmp_path / "core" / "ranking_orchestrator.py", "x = 1\n")

    payload = run_campaign(tmp_path, tmp_path / "campaign.json")

    assert payload["shadow_cycle"]["mismatch_count"] == 1
    assert payload["verdict"]["shadow_parity"] is False
