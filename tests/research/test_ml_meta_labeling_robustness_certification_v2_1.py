from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_runner():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_ml_meta_labeling_robustness_certification_v2_1.py"
    spec = importlib.util.spec_from_file_location("ml_cert_v21", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ml_meta_labeling_v2_1_rejects_on_concrete_replay_without_external_calls():
    runner = _load_runner()

    verdict = runner.main()

    assert verdict == "ML_META_LABELING_SIGNAL_REJECTED_ON_CONCRETE_REPLAY"
    out = runner.OUT
    hash_report = json.loads((out / "frozen_hash_verification_report.json").read_text())
    coverage = json.loads((out / "coverage_report.json").read_text())
    concrete = json.loads((out / "concrete_economic_report.json").read_text())
    audit = json.loads((out / "independent_audit.json").read_text())

    assert hash_report["status"] == "PASS"
    assert coverage["concrete_trades"] == 300
    assert coverage["coverage_gate_passed"] is True
    assert concrete["expectancy"] < 0
    assert concrete["profit_factor"] < 1.2
    assert audit["broker_api_called"] is False
    assert audit["provider_api_called"] is False
    assert audit["production_files_modified"] is False
    assert (out / "concrete_strike_mapping_ledger.parquet").exists()
    assert (out / "concrete_holdout_trade_ledger.parquet").exists()
    assert (out / "delayed_entry_report.json").exists()
    assert len(list(out.glob("feature_family_ablation_*.json"))) == 4
