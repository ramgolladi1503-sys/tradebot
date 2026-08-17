from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "research" / "analyze_advisory_candidate_outcomes_postclose_v1.py"
spec = importlib.util.spec_from_file_location("advisory_outcomes_v1", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def candidate(**overrides):
    row = {
        "candidate_id": "c1",
        "selected_option_instrument": "NFO|NIFTY|2026-08-18|24000|PE",
        "expiry": "2026-08-18",
        "signal_epoch": 100.0,
        "direction": "BUY_PUT",
        "entry_price": 100.0,
        "stop_loss_price": 80.0,
        "target_price": 120.0,
        "stage_status": "blocked",
        "advisory": True,
        "execution_allowed": False,
    }
    row.update(overrides)
    return row


def obs(ts, ltp, **extra):
    row = {"instrument_key": "NFO|NIFTY|2026-08-18|24000|PE", "observed_epoch": ts, "ltp": ltp}
    row.update(extra)
    return row


def test_same_timestamp_as_signal_is_excluded_and_future_target_is_used():
    payload = mod.analyze([candidate()], [obs(100.0, 130), obs(101.0, 121)])
    outcome = payload["outcomes"][0]
    assert outcome["outcome_status"] == "TARGET_TOUCHED"
    assert outcome["first_hit_epoch"] == 101.0
    assert outcome["observation_count"] == 1
    assert payload["strict_future_only"] is True


def test_rejected_candidate_is_never_promoted_to_trade_or_realized_pnl():
    payload = mod.analyze([candidate()], [obs(101.0, 125)])
    outcome = payload["outcomes"][0]
    assert outcome["source_execution_allowed"] is False
    assert outcome["counterfactual_only"] is True
    assert outcome["realized_trade"] is False
    assert outcome["realized_pnl"] is None
    assert outcome["touch_is_realized_pnl"] is False
    assert payload["rejected_candidate_is_trade"] is False


def test_first_hit_ordering_is_causal():
    payload = mod.analyze([candidate()], [obs(101.0, 79), obs(102.0, 130)])
    outcome = payload["outcomes"][0]
    assert outcome["outcome_status"] == "STOP_TOUCHED"
    assert outcome["first_hit_epoch"] == 101.0


def test_same_timestamp_target_and_stop_is_ambiguous():
    payload = mod.analyze([candidate()], [obs(101.0, 100, bid=79, ask=121)])
    assert payload["outcomes"][0]["outcome_status"] == "AMBIGUOUS_SAME_TIMESTAMP"


def test_exact_instrument_mapping_required_and_wrong_instrument_ignored():
    payload = mod.analyze([candidate()], [{"instrument_key": "OTHER", "observed_epoch": 101.0, "ltp": 130}])
    assert payload["outcomes"][0]["outcome_status"] == "NO_FUTURE_OBSERVATIONS"


def test_missing_expiry_remains_unavailable_not_zero():
    payload = mod.analyze([candidate(expiry=None)], [obs(101.0, 130)])
    outcome = payload["outcomes"][0]
    assert outcome["outcome_status"] == "UNAVAILABLE_REQUIRED_FIELDS"
    assert "expiry" in outcome["missing_fields"]
    assert outcome["expiry"] is None
    assert payload["missing_values_coerced_to_zero"] is False


def test_duplicate_candidate_ids_fail_closed():
    with pytest.raises(mod.AnalysisError, match="DUPLICATE_CANDIDATE_ID"):
        mod.analyze([candidate(), candidate()], [])


def test_output_is_write_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Replace repo-root resolution only for this unit boundary; write-once semantics remain real.
    monkeypatch.setattr(mod.Path, "resolve", Path.resolve)
    target = tmp_path / "out.json"
    mod._write_once(target, {"ok": True})
    with pytest.raises(mod.AnalysisError, match="OUTPUT_ALREADY_EXISTS"):
        mod._write_once(target, {"ok": False})


def test_safety_flags_are_all_false():
    payload = mod.analyze([], [])
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    assert payload["paper_authorized"] is False
    assert payload["live_authorized"] is False
    assert payload["structural_edge_certified"] is False
