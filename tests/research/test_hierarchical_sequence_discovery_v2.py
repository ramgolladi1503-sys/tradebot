import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_hierarchical_sequence_discovery_v2.py"


def run_to(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_hierarchy_is_frozen_and_deterministic_before_outcomes():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        ontology = load(out, "frozen_event_ontology.json")
        det = load(out, "hierarchy_determinism_report.json")
        audit = load(out, "independent_audit.json")

    assert ontology["outcome_informed"] is False
    assert det["status"] == "PASS"
    assert audit["hierarchy_mapping_used_no_future_labels"] is True


def test_frequency_gate_failure_blocks_outcome_reports():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        verdict = load(out, "final_verdict.json")
        gate = load(out, "frequency_gate_report.json")
        outcome = load(out, "outcome_report.json")

    assert verdict["final_verdict"] == "NO_HIERARCHICAL_MOTIF_PASSED_FREQUENCY_GATE"
    assert gate["passed_motifs"] == 0
    assert outcome["status"] == "NOT_RUN"


def test_required_deliverables_exclude_provider_and_broker_work():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        pre = load(out, "pre_change_manifest.json")
        audit = load(out, "independent_audit.json")

    assert pre["provider_calls"] is False
    assert pre["broker_calls"] is False
    assert pre["outcomes_computed"] is False
    assert audit["frequency_gate_unchanged"] is True
