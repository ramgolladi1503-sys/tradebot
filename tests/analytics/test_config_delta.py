from __future__ import annotations

import json
from pathlib import Path

from core.analytics.config_delta import build_config_delta_proposal, write_config_delta


def _base_report(*, sessions: int, window_days: int, sample_size: int, effect_size: float) -> dict:
    return {
        "day": "2026-02-27",
        "summary": {
            "sessions_count": sessions,
            "window_days": window_days,
        },
        "metrics": {
            "gates": {
                "baseline_hit_rate": 0.41,
                "top_bad_gates": [
                    {
                        "gate_reason": "spread_guard",
                        "count": sample_size,
                        "hits": 18,
                        "sls": 4,
                        "hit_rate": 0.63,
                        "effect_size_vs_hit_baseline": effect_size,
                    }
                ],
                "top_protective_gates": [
                    {
                        "gate_reason": "risk_guard",
                        "count": sample_size,
                        "hits": 6,
                        "sls": 20,
                        "sl_rate": 0.67,
                        "effect_size_vs_sl_baseline": max(effect_size, 0.2),
                    }
                ],
            },
            "feed": {
                "feed_block_rejects": sample_size,
                "missed_edge_due_to_feed": 22,
                "missed_edge_due_to_other": 12,
                "feed_related_share_of_missed_edge": 0.65,
                "rejects_by_feed_group": {"OPT:NIFTY": 18, "OPT:BANKNIFTY": 11},
            },
            "outcomes": {
                "saved_count": 7,
                "missed_edge_count": 34,
            },
        },
    }


def test_no_proposal_when_confidence_fails():
    report = _base_report(sessions=1, window_days=1, sample_size=12, effect_size=0.10)
    proposal = build_config_delta_proposal(report)
    assert proposal["proposals"] == []
    assert isinstance(proposal.get("no_proposal_reason"), str)
    assert "NO PROPOSAL" in proposal["no_proposal_reason"]


def test_proposal_created_when_confidence_passes():
    report = _base_report(sessions=3, window_days=3, sample_size=45, effect_size=0.22)
    proposal = build_config_delta_proposal(report)
    assert len(proposal["proposals"]) >= 1
    first = proposal["proposals"][0]
    assert first["justification"]["sample_size"] >= 30
    assert abs(float(first["justification"]["effect_size"])) >= 0.15
    assert first["justification"]["sessions"] >= 2
    assert isinstance(first["rollback_plan"], list) and first["rollback_plan"]
    assert "NO AUTO-APPLY. HUMAN REVIEW REQUIRED." in first["notes"]


def test_scope_never_live_without_extra_rule():
    report = _base_report(sessions=6, window_days=3, sample_size=60, effect_size=0.40)
    proposal = build_config_delta_proposal(report)
    assert proposal["proposals"]
    for row in proposal["proposals"]:
        assert row["change"]["scope"] != "LIVE"


def test_write_outputs_atomic_and_valid(tmp_path: Path):
    report = _base_report(sessions=3, window_days=3, sample_size=50, effect_size=0.20)
    proposal = build_config_delta_proposal(report)
    md_path, json_path = write_config_delta(proposal, tmp_path / "runtime" / "analytics" / "reports")
    assert md_path.exists()
    assert json_path.exists()
    assert "Config Delta Proposal" in md_path.read_text(encoding="utf-8")
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["day"] == "2026-02-27"
    assert not list((tmp_path / "runtime" / "analytics" / "reports" / "2026-02-27").glob("*.tmp"))
