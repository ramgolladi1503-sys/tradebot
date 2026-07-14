from __future__ import annotations

from pathlib import Path


def test_one_replay_event_naturally_reaches_candidate_emission():
    report = Path("docs/research/one_candidate_replay_event_slice.md")
    assert report.exists(), "missing replay event slice evidence report"

    text = report.read_text(encoding="utf-8")
    assert "Verdict: `FULLY_PROVEN_FROM_PERSISTED_RUNTIME_ARTIFACTS`" in text
    assert "NIFTY-2026-07-07-24150-PE-mean-reversion-1782975597" in text
    assert ".runtime/runtime_candidate_handoff_latest.json" in text
    assert ".runtime/opportunities/ranked_pipeline_latest.json" in text
