import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_nifty_futures_historical_acquisition_v1.py"


def run_fixture(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--mode", "fixture", "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_fixture_acquisition_is_partial_and_never_certified_full():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_fixture(out)
        verdict = load(out, "final_verdict.json")
        coverage = load(out, "coverage_certification.json")

    assert verdict["final_verdict"] == "NIFTY_FUTURES_HISTORY_PARTIALLY_CERTIFIED"
    assert coverage["total_rows"] > 0
    assert coverage["minimum_target_met"] is False
    assert coverage["unique_expiries"] < 12


def test_request_ledger_is_frozen_before_acquisition_and_no_secret_flags():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_fixture(out)
        pre = load(out, "pre_change_manifest.json")
        ledger = load(out, "frozen_acquisition_ledger.json")
        contract = load(out, "acquisition_contract.json")

    assert ledger["status"] == "FROZEN_BEFORE_PROVIDER_REQUEST"
    assert pre["token_stored"] is False
    assert pre["broker_api_called"] is False
    assert "synthetic_contracts" in ledger["prohibited"]
    assert contract["overwrite_policy"] == "fail_if_existing"


def test_audit_blocks_synthetic_and_continuous_series_operations():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_fixture(out)
        audit = load(out, "independent_audit.json")
        front = load(out, "front_month_mapping.json")

    assert audit["no_synthetic_rows"] is True
    assert audit["no_forward_fill"] is True
    assert audit["no_back_adjustment"] is True
    assert front["causal"] is True
