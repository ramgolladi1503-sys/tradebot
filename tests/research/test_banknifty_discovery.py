from datetime import datetime
import hashlib
import json

import pytest

from research.banknifty_v1.discovery import build_sessions, evaluate, load_artifact
from research.governance.index_research_contract import ResearchOutcome, ResearchSpec


SPEC = ResearchSpec("BANKNIFTY", "next_session_open_gap", "09:14:59", "dev", "oos", ("prior_close_gap_baseline",), ("sign_permutation",), "required")


def artifact(tmp_path):
    candles = []
    for day, close, opening in [("2023-01-02", 100.0, 101.0), ("2023-01-03", 102.0, 101.5), ("2023-01-04", 103.0, 104.0), ("2023-01-05", 105.0, 104.5), ("2023-01-06", 106.0, 107.0), ("2023-01-09", 108.0, 107.5)]:
        candles.extend([[f"{day}T15:29:00+05:30", close, close, close, close, 0, 0], [f"{day}T09:15:00+05:30", opening, opening, opening, opening, 0, 0]])
    path = tmp_path / "banknifty.json"
    path.write_text(json.dumps({"data": {"candles": candles}}), encoding="utf-8")
    return path


def test_artifact_sha_and_date_session_construction(tmp_path):
    path = artifact(tmp_path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = load_artifact(path, expected_sha256=sha)
    assert len(build_sessions([loaded])) == 5
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        load_artifact(path, expected_sha256="0" * 64)


def test_evaluation_keeps_oos_separate_and_returns_honest_no_edge(tmp_path):
    path = artifact(tmp_path)
    loaded = load_artifact(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    report = evaluate(SPEC, [loaded])
    assert report.outcome is ResearchOutcome.NO_STRUCTURAL_EDGE_FOUND
    assert report.counts["oos"] >= 1
    assert report.search_pressure["oos_untouched"] is True


def test_future_or_missing_artifact_data_does_not_become_zero(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"data": {"candles": []}}), encoding="utf-8")
    loaded = load_artifact(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    report = evaluate(SPEC, [loaded])
    assert report.outcome is ResearchOutcome.BLOCKED_DATA
