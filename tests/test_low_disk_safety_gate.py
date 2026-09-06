from pathlib import Path

from core.low_disk_safety_gate import derive_budget, evaluate, validate_contract
import pytest


def test_budget_is_additive_and_reproducible():
    budget = derive_budget(baseline_bytes=100, observed_bytes_per_second=2.5,
                           remaining_session_seconds=10, peak_transient_bytes=7,
                           shutdown_reserve_bytes=11)
    assert budget.remaining_session_growth_bytes == 25
    assert budget.required_free_bytes == 143


def test_negative_inputs_fail_closed():
    try:
        derive_budget(baseline_bytes=-1, observed_bytes_per_second=1,
                      remaining_session_seconds=1, peak_transient_bytes=0,
                      shutdown_reserve_bytes=0)
    except ValueError as exc:
        assert str(exc) == "DISK_BUDGET_INPUT_NEGATIVE"
    else:
        raise AssertionError("negative budget input was accepted")


def test_missing_filesystem_is_unknown():
    budget = derive_budget(baseline_bytes=1, observed_bytes_per_second=0,
                           remaining_session_seconds=0, peak_transient_bytes=0,
                           shutdown_reserve_bytes=0)
    decision = evaluate(Path("/definitely/missing/tradebot-disk"), budget)
    assert decision.verdict == "UNKNOWN"


def test_contract_validator_accepts_frozen_contract():
    import json
    contract = json.loads(Path("TRADEBOT_LOW_DISK_SAFETY_CONTRACT_V1.json").read_text())
    assert validate_contract(contract) == (True, ())


def test_contract_validator_rejects_order_authority():
    assert validate_contract({"order_authority": True})[0] is False


@pytest.mark.parametrize("kwargs", [
    dict(baseline_bytes=-1, observed_bytes_per_second=0, remaining_session_seconds=0, peak_transient_bytes=0, shutdown_reserve_bytes=0),
    dict(baseline_bytes=0, observed_bytes_per_second=-1, remaining_session_seconds=0, peak_transient_bytes=0, shutdown_reserve_bytes=0),
    dict(baseline_bytes=0, observed_bytes_per_second=0, remaining_session_seconds=-1, peak_transient_bytes=0, shutdown_reserve_bytes=0),
    dict(baseline_bytes=0, observed_bytes_per_second=0, remaining_session_seconds=0, peak_transient_bytes=-1, shutdown_reserve_bytes=0),
    dict(baseline_bytes=0, observed_bytes_per_second=0, remaining_session_seconds=0, peak_transient_bytes=0, shutdown_reserve_bytes=-1),
])
def test_five_negative_budget_controls(kwargs):
    with pytest.raises(ValueError, match="DISK_BUDGET_INPUT_NEGATIVE"):
        derive_budget(**kwargs)


@pytest.mark.parametrize("free,required", [(0, 1), (1, 2), (10, 11), (99, 100), (100, 101)])
def test_five_insufficient_space_controls(monkeypatch, free, required):
    monkeypatch.setattr("core.low_disk_safety_gate.shutil.disk_usage", lambda _: type("U", (), {"free": free})())
    decision = evaluate(Path("/tmp"), derive_budget(baseline_bytes=required, observed_bytes_per_second=0, remaining_session_seconds=0, peak_transient_bytes=0, shutdown_reserve_bytes=0))
    assert decision.verdict == "BLOCKED"


@pytest.mark.parametrize("path", [Path("/not/a/path"), Path("/missing"), Path("/gone")])
def test_three_unknown_filesystem_controls(monkeypatch, path):
    def fail(_):
        raise OSError("missing")
    monkeypatch.setattr("core.low_disk_safety_gate.shutil.disk_usage", fail)
    decision = evaluate(path, derive_budget(baseline_bytes=1, observed_bytes_per_second=0, remaining_session_seconds=0, peak_transient_bytes=0, shutdown_reserve_bytes=0))
    assert decision.verdict == "UNKNOWN"
