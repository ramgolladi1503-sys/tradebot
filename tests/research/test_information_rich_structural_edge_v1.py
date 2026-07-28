import json
import subprocess
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_information_rich_structural_edge_v1.py"


def run_to(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_information_first_contract_and_hypothesis_limit():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        label = load(out, "expansion_label_contract.json")
        hyps = load(out, "frozen_hypotheses.json")
        ranking = pd.read_csv(out / "feature_ranking.csv")

    assert label["labels_frozen_before_hypotheses"] is True
    assert hyps["frozen_before_holdout"] is True
    assert hyps["count"] <= 3
    assert len(ranking) >= 5
    assert "vwap_cross_reclaim" not in set(ranking["feature"])


def test_campaign_boundaries_no_external_or_production_actions():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        pre = load(out, "pre_change_manifest.json")
        audit = load(out, "independent_audit.json")

    assert pre["provider_calls"] is False
    assert pre["broker_calls"] is False
    assert pre["algotest_called"] is False
    assert pre["production_changes"] is False
    assert audit["closed_lanes_not_reopened"] is True


def test_survivor_report_matches_final_verdict():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        survivors = load(out, "survivor_report.json")
        final = load(out, "final_verdict.json")

    if survivors["count"] == 0:
        assert final["final_verdict"] == "NO_INFORMATION_RICH_STRUCTURAL_EDGE_FOUND"
        assert survivors["executable_strategy_specs"] == []
    else:
        assert final["final_verdict"] == "INFORMATION_RICH_STRUCTURAL_EDGE_FOUND"
