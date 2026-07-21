from __future__ import annotations

from pathlib import Path


def test_independent_extractor_does_not_import_original_extractor():
    source = Path("research/opening_dislocation_reversal/fresh_epoch_reconciliation_v3.py").read_text()
    assert "fresh_epoch_acquisition" not in source
    assert "strategy" not in source.lower()
    assert "candidate" not in source.lower()
    assert "outcome" not in source.lower()


def test_v2_auditor_coverage_is_marked_incomplete():
    audit = Path("research/opening_dislocation_reversal/data_acquisition/independent_acquisition_audit_v2.json").read_text()
    assert "row_conservation" not in audit


def test_no_raw_data_committed_in_acquisition_artifacts():
    raw_files = list(Path("research/opening_dislocation_reversal/data_acquisition").glob("*.parquet"))
    assert raw_files == []


def test_historical_artifacts_are_retained():
    assert Path("research/opening_dislocation_reversal/data_acquisition/partial_fresh_session_manifest_v2.json").exists()
    assert Path("research/opening_dislocation_reversal/data_acquisition/final_verdict.json").exists()
