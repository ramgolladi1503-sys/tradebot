from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pandas as pd

def test_missing_input_to_option_truth_validator_does_not_return_ready(tmp_path: Path) -> None:
    validator = Path("scripts/validate_live_option_truth_capture.py")
    out = tmp_path / "out1"
    subprocess.run([str(validator), "--out-dir", str(out)], capture_output=True)
    report = json.loads(list(out.glob("*.json"))[0].read_text())
    assert report["verdict"] == "NOT_READY_FOR_EXECUTABLE_REPLAY"

def test_missing_bid_ask_returns_missing_bid_ask(tmp_path: Path) -> None:
    validator = Path("scripts/validate_live_option_truth_capture.py")
    out = tmp_path / "out2"
    inp = tmp_path / "in2.csv"
    pd.DataFrame([{"ltp": 100, "candidate_id": 1}]).to_csv(inp, index=False)
    subprocess.run([str(validator), "--input", str(inp), "--out-dir", str(out)], capture_output=True)
    report = json.loads(list(out.glob("*.json"))[0].read_text())
    assert report["verdict"] == "MISSING_BID_ASK"

def test_missing_option_ltp_returns_missing_option_ltp(tmp_path: Path) -> None:
    validator = Path("scripts/validate_live_option_truth_capture.py")
    out = tmp_path / "out3"
    inp = tmp_path / "in3.csv"
    pd.DataFrame([{"candidate_id": 1, "bid": 99, "ask": 101}]).to_csv(inp, index=False)
    subprocess.run([str(validator), "--input", str(inp), "--out-dir", str(out)], capture_output=True)
    report = json.loads(list(out.glob("*.json"))[0].read_text())
    assert report["verdict"] == "MISSING_OPTION_LTP"

def test_missing_quote_age_sec_returns_missing_quote_age(tmp_path: Path) -> None:
    validator = Path("scripts/validate_live_option_truth_capture.py")
    out = tmp_path / "out4"
    inp = tmp_path / "in4.csv"
    pd.DataFrame([{"candidate_id": 1, "ltp": 100, "bid": 99, "ask": 101, "spread": 2}]).to_csv(inp, index=False)
    subprocess.run([str(validator), "--input", str(inp), "--out-dir", str(out)], capture_output=True)
    report = json.loads(list(out.glob("*.json"))[0].read_text())
    assert report["verdict"] == "MISSING_QUOTE_AGE"

def test_missing_candidate_linkage_returns_missing_candidate_linkage(tmp_path: Path) -> None:
    validator = Path("scripts/validate_live_option_truth_capture.py")
    out = tmp_path / "out5"
    inp = tmp_path / "in5.csv"
    pd.DataFrame([{"ltp": 100, "bid": 99, "ask": 101, "spread": 2, "quote_age_sec": 1}]).to_csv(inp, index=False)
    subprocess.run([str(validator), "--input", str(inp), "--out-dir", str(out)], capture_output=True)
    report = json.loads(list(out.glob("*.json"))[0].read_text())
    assert report["verdict"] == "MISSING_CANDIDATE_LINKAGE"

def test_no_future_outcome_path_prevents_live_shadow_readiness(tmp_path: Path) -> None:
    tracker = Path("scripts/check_live_shadow_outcomes.py")
    out = tmp_path / "out6"
    inp = tmp_path / "in6.csv"
    pd.DataFrame([{"candidate_id": 1, "instrument_id": 2, "strategy": "s", "entry_timestamp": "2026-06-29"}]).to_csv(inp, index=False)
    subprocess.run([str(tracker), "--input", str(inp), "--out-dir", str(out)], capture_output=True)
    report = json.loads(list(out.glob("*.json"))[0].read_text())
    assert report["verdict"] == "LIVE_SHADOW_NOT_READY"

def test_edge_ladder_cannot_produce_executable_replay_readiness_without_proof(tmp_path: Path) -> None:
    ladder = Path("scripts/generate_edge_ladder_report.py")
    out = tmp_path / "out7"
    subprocess.run([str(ladder), "--out-dir", str(out), "--audit-dir", str(tmp_path), "--evidence-dir", str(tmp_path)], capture_output=True)
    report = json.loads(list(out.glob("*.json"))[0].read_text())
    assert report["final_verdict"] != "EXECUTABLE_REPLAY_READY"
    assert report["final_verdict"] != "LIVE_SHADOW_POSITIVE"
    assert report["executable_replay_possible"] is False
    
def test_no_live_trading_behavior_changes_shadow_tracker() -> None:
    tracker = Path("scripts/check_live_shadow_outcomes.py").read_text()
    assert "broker" not in tracker.lower()
    assert "place_order" not in tracker.lower()
    assert "kite" not in tracker.lower()
