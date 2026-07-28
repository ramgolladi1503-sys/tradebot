import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_market_state_sequence_discovery_v1.py"


def run_to(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_blocks_before_motif_discovery_when_constituents_uncertified():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        verdict = load(out, "final_verdict.json")
        constituent = load(out, "constituent_data_certification_report.json")
        motif = load(out, "motif_catalogue.json")

    assert verdict["final_verdict"] == "CONSTITUENT_OR_OPTION_INPUTS_INSUFFICIENT"
    assert constituent["certification_result"] == "FAIL"
    assert motif["motifs"] == []


def test_no_outcome_reports_run_without_frozen_motifs():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        freq = load(out, "frequency_gate_report.json")
        outcome = load(out, "outcome_report.json")
        holdout = load(out, "holdout_report.json")

    assert freq["passed_motifs"] == 0
    assert outcome["status"] == "NOT_RUN"
    assert holdout["status"] == "NOT_RUN"


def test_audit_honors_closed_registry_and_no_reuse():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        audit = load(out, "independent_audit.json")
        pre = load(out, "pre_change_manifest.json")

    assert audit["prior_closeout_registry_honored"] is True
    assert audit["no_closed_mechanism_reused"] is True
    assert pre["broker_calls"] is False
    assert pre["pnl_or_outcome_inspection"] is False
