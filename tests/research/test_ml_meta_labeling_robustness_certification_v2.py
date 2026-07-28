import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_ml_meta_labeling_robustness_certification_v2.py"


def load(path: Path):
    with path.open() as f:
        return json.load(f)


def test_certification_fails_closed_when_frozen_model_artifacts_are_missing():
    with tempfile.TemporaryDirectory() as td:
        subprocess.check_call(["python", str(SCRIPT)], cwd=ROOT)
        out = ROOT / "research/ml_meta_labeling_robustness_certification_v2"
        final = load(out / "final_verdict.json")
        audit = load(out / "independent_audit.json")
        reconciliation = load(out / "certification_input_reconciliation.json")

    assert final["final_verdict"] == "INVALID_ML_META_LABELING_CERTIFICATION_INPUTS"
    assert "trained_model" in final["missing_required_artifacts"]
    assert "calibration_object" in final["missing_required_artifacts"]
    assert audit["no_retraining"] is True
    assert audit["provider_calls"] is False
    assert audit["broker_calls"] is False
    assert reconciliation["no_threshold_reselection_performed"] is True
