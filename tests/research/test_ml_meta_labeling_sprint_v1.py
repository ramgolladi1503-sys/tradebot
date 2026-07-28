import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_ml_meta_labeling_sprint_v1.py"


def load(path: Path):
    with path.open() as f:
        return json.load(f)


def test_ml_meta_labeling_sprint_is_conservative_and_research_only():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)
        final = load(out / "final_verdict.json")
        audit = load(out / "independent_audit.json")
        features = load(out / "feature_contract.json")
        labels = load(out / "label_contract.json")
        balance = load(out / "class_balance_report.json")

    assert final["final_verdict"] in {
        "ML_META_LABELING_USEFUL_CASE_FOUND",
        "ML_META_LABELING_SIGNAL_FOUND_NOT_YET_ROBUST",
        "NO_ML_META_LABELING_VALUE_FOUND",
        "ML_META_LABELING_INPUTS_INSUFFICIENT",
        "INVALID_ML_META_LABELING_PIPELINE",
    }
    assert final["final_verdict"] == "ML_META_LABELING_SIGNAL_FOUND_NOT_YET_ROBUST"
    assert final["survivor_useful_case"] is False
    assert final["required_incomplete_gates"]["one_bar_delayed_entry_survival"] is True
    assert audit["provider_calls"] is False
    assert audit["broker_calls"] is False
    assert audit["algotest_called"] is False
    assert audit["production_changes"] is False
    assert features["feature_count"] <= 60
    assert labels["primary_label"] == "TARGET_30_BEFORE_STOP_15_WITHIN_30M"
    assert balance["eligible"] >= 300
