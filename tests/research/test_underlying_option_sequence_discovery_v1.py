import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_underlying_option_sequence_discovery_v1.py"


def run_to(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_reduced_universe_runs_without_breadth_or_futures_claims():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        audit = load(out, "independent_audit.json")
        state = load(out, "state_vector_contract.json")

    assert audit["unsupported_breadth_claims_excluded"] is True
    assert audit["unsupported_microstructure_claims_excluded"] is True
    assert state["no_constituents"] is True
    assert state["no_futures"] is True


def test_outcomes_are_not_run_when_frequency_gate_fails():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        verdict = load(out, "final_verdict.json")
        frequency = load(out, "frequency_gate_report.json")
        outcome = load(out, "outcome_report.json")

    assert verdict["final_verdict"] == "NO_MOTIF_PASSED_FREQUENCY_GATE"
    assert frequency["passed_motifs"] == 0
    assert outcome["status"] == "NOT_RUN"


def test_event_stream_and_motifs_are_pre_outcome_artifacts():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        events = load(out, "event_stream_manifest.json")
        motifs = load(out, "motif_catalogue.json")
        pre = load(out, "pre_change_manifest.json")

    assert events["row_count"] > 0
    assert len(motifs["motifs"]) > 0
    assert pre["provider_acquisition"] is False
    assert pre["broker_calls"] is False
