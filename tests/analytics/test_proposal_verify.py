from __future__ import annotations

import json
from pathlib import Path

from core.analytics.proposal_verify import (
    load_json,
    load_snapshot,
    verify_proposal,
    write_verification,
)


def _proposal_item(
    *,
    proposal_id: str = "p1",
    key: str = "QUOTE_MAX_SPREAD_PCT",
    proposed: object = 0.0045,
    scope: str = "PAPER_ONLY",
    sample_size: int = 120,
    effect_size: float = 0.25,
    sessions: int = 4,
) -> dict:
    return {
        "id": proposal_id,
        "area": "quote_quality",
        "change": {
            "key": key,
            "current": None,
            "proposed": proposed,
            "scope": scope,
        },
        "justification": {
            "sample_size": sample_size,
            "effect_size": effect_size,
            "sessions": sessions,
            "baseline_hit_rate": 0.41,
            "gate_hit_rate": 0.63,
            "missed_winners": 18,
            "saved_from_sl": 4,
        },
        "risk": {
            "expected_trade_quality_risk": "MEDIUM",
            "expected_drawdown_risk": "MEDIUM",
            "failure_modes": [],
        },
        "rollout_plan": ["paper test"],
        "rollback_plan": ["revert"],
        "notes": "NO AUTO-APPLY. HUMAN REVIEW REQUIRED.",
    }


def _proposal_doc(*items: dict, window_days: int = 3) -> dict:
    return {
        "day": "2026-02-27",
        "window_days": window_days,
        "proposals": list(items),
        "no_proposal_reason": None,
    }


def _snapshot_doc() -> dict:
    return {
        "QUOTE_MAX_SPREAD_PCT": 0.0035,
        "STALE_QUOTE_AGE_SEC": 2.0,
        "DEPTH_WINDOW_SIZE": 120,
        "NESTED": {"SAFE_LEVEL": 3},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")


def test_pass_valid_proposal(tmp_path: Path):
    proposal = _proposal_doc(_proposal_item())
    snapshot = _snapshot_doc()
    report = verify_proposal(proposal, snapshot)
    assert report["status"] == "PASS"
    assert report["summary"]["passed"] == 1
    assert report["summary"]["failed"] == 0


def test_fail_missing_key(tmp_path: Path):
    proposal = _proposal_doc(_proposal_item(key="UNKNOWN_KEY"))
    snapshot = _snapshot_doc()
    report = verify_proposal(proposal, snapshot)
    assert report["status"] == "FAIL"
    result = report["results"][0]
    assert result["status"] == "FAIL"
    check = next(c for c in result["checks"] if c["name"] == "key_exists")
    assert check["status"] == "FAIL"


def test_fail_type_mismatch(tmp_path: Path):
    proposal = _proposal_doc(_proposal_item(proposed="0.0045"))
    snapshot = _snapshot_doc()
    report = verify_proposal(proposal, snapshot)
    assert report["status"] == "FAIL"
    result = report["results"][0]
    check = next(c for c in result["checks"] if c["name"] == "type_match")
    assert check["status"] == "FAIL"


def test_warn_or_fail_range_check(tmp_path: Path):
    proposal = _proposal_doc(_proposal_item(proposed=0.08))
    snapshot = _snapshot_doc()
    report = verify_proposal(proposal, snapshot)
    assert report["status"] == "WARN"
    result = report["results"][0]
    check = next(c for c in result["checks"] if c["name"] == "value_range")
    assert check["status"] == "WARN"


def test_fail_live_scope_without_strict_requirements(tmp_path: Path):
    proposal = _proposal_doc(_proposal_item(scope="LIVE", sample_size=99, effect_size=0.21, sessions=5), window_days=4)
    snapshot = _snapshot_doc()
    report = verify_proposal(proposal, snapshot)
    assert report["status"] == "FAIL"
    result = report["results"][0]
    check = next(c for c in result["checks"] if c["name"] == "scope_rule")
    assert check["status"] == "FAIL"


def test_observed_current_populated(tmp_path: Path):
    proposal = _proposal_doc(_proposal_item())
    snapshot = _snapshot_doc()
    report = verify_proposal(proposal, snapshot)
    assert report["results"][0]["observed_current"] == 0.0035

    out_dir = tmp_path / "runtime" / "analytics" / "reports" / "2026-02-27"
    md_path, json_path = write_verification(report, out_dir)
    assert md_path.exists()
    assert json_path.exists()

    loaded = load_json(json_path)
    assert loaded["results"][0]["observed_current"] == 0.0035

    snapshot_path = tmp_path / "snapshot.json"
    _write_json(snapshot_path, snapshot)
    loaded_snapshot = load_snapshot(snapshot_path)
    assert loaded_snapshot["QUOTE_MAX_SPREAD_PCT"] == 0.0035
