import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_ml_meta_labeling_sprint_v1.py"


def load(path: Path):
    with path.open() as f:
        return json.load(f)


def test_reproducible_sprint_persists_certification_artifacts():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)
        final = load(out / "final_verdict.json")
        replay = load(out / "serialization_replay_report.json")
        comparison = load(out / "reproduction_comparison_table.json")
        audit = load(out / "independent_audit.json")

        required = [
            "candidate_level_dataset.parquet",
            "trained_model.joblib",
            "calibration_object.joblib",
            "preprocessor.joblib",
            "frozen_selection_threshold.json",
            "train_predictions.parquet",
            "validation_predictions.parquet",
            "holdout_predictions.parquet",
        ]
        for name in required:
            assert (out / name).exists(), name

    assert final["final_verdict"] == "ML_META_LABELING_SPRINT_REPRODUCED_AND_FROZEN"
    assert replay["status"] == "PASS"
    assert replay["selected_candidate_ids_identical"] is True
    assert comparison["all_acceptance_passed"] is True
    assert audit["stored_model_reproduces_predictions"] is True
    assert audit["provider_calls"] is False
    assert audit["broker_calls"] is False
