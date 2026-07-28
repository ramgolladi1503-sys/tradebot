import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_certified_futures_options_information_layer_v1.py"


def run_to(path: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(path)], cwd=ROOT)


def load(path: Path, name: str):
    with (path / name).open() as f:
        return json.load(f)


def test_futures_gate_fails_closed_without_synthetic_warehouse():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        verdict = load(out, "final_verdict.json")
        futures = load(out, "futures_warehouse_manifest.json")
        joint = load(out, "joint_warehouse_manifest.json")
        capability = load(out, "capability_gate_matrix.json")

    assert verdict["final_verdict"] == "FUTURES_DATA_INSUFFICIENT"
    assert futures["status"] == "NOT_BUILT"
    assert futures["synthetic_values"] is False
    assert joint["blocking_gate"] == "MISSING_FUTURES_LEG"
    assert capability["mandatory"]["synchronized_nifty_futures_ohlc"] == "UNSUPPORTED"


def test_no_outcome_or_provider_actions_are_recorded():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        pre = load(out, "pre_change_manifest.json")
        provider = load(out, "provider_feasibility_report.json")
        audit = load(out, "independent_audit.json")

    assert pre["broker_api_called"] is False
    assert pre["orders_placed"] is False
    assert pre["pnl_or_outcome_inspection"] is False
    assert provider["policy"]["provider_calls_made"] is False
    assert provider["policy"]["secrets_read_or_stored"] is False
    assert audit["no_pnl_or_outcome_inspection"] is True


def test_two_directory_determinism_for_semantic_outputs():
    with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
        out1 = Path(td1)
        out2 = Path(td2)
        run_to(out1)
        run_to(out2)
        d1 = load(out1, "determinism_report.json")
        d2 = load(out2, "determinism_report.json")

    assert d1["aggregate_semantic_hash"] == d2["aggregate_semantic_hash"]
    assert d1["status"] == "PASS"
