import ast
import json
import shutil

import pandas as pd

from research.rsi2_mean_reversion import independent_publication_oracle_v2 as oracle


def test_oracle_does_not_import_publication_gate_helpers():
    source = oracle.Path("research/rsi2_mean_reversion/independent_publication_oracle_v2.py").read_text()
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    assert "research.rsi2_mean_reversion.publication_gate" not in imports
    assert "from research.rsi2_mean_reversion.publication_gate" not in source


def test_independent_generator_reproduces_v1_or_detects_mismatch():
    df = oracle.independent_random_replicates()
    comparison = oracle.v1_comparison(df)

    assert comparison["comparison"] == "NUMERICALLY_EQUIVALENT_WITH_DOCUMENTED_SERIALIZATION_DIFFERENCE"
    assert len(df) == 1000
    assert df["completed_trade_count"].eq(127).all()
    assert df["duplicate_count"].eq(0).all()
    assert df["overlap_count"].eq(0).all()
    assert df["seed"].iloc[0] == 20260721
    assert df["seed"].iloc[-1] == 20261720


def test_one_row_mutation_changes_random_semantic_hash(tmp_path):
    source = oracle.V2 / "independent_random_replicate_hashes_v2.csv"
    target = tmp_path / "replicates.csv"
    shutil.copy2(source, target)
    before = oracle.sha256_file(target)
    frame = pd.read_csv(target)
    frame.loc[0, "expectancy"] = frame.loc[0, "expectancy"] + 0.01
    frame.to_csv(target, index=False)

    assert oracle.sha256_file(target) != before


def test_wrong_verdict_fails_oracle_expectation(tmp_path):
    report = json.loads((oracle.V2 / "final_publication_report_v2.json").read_text())
    report["overall_research_verdict"] = "STRUCTURAL_EDGE_SUPPORTED"
    target = tmp_path / "bad_report.json"
    target.write_text(json.dumps(report))

    loaded = json.loads(target.read_text())
    assert loaded["overall_research_verdict"] != oracle.decide(
        oracle.random_summary(oracle.independent_random_replicates()),
        oracle.control_truth(oracle.random_summary(oracle.independent_random_replicates())),
        oracle.trend_filter_audit(),
        oracle.tradable_inventory(),
    )["overall_research_verdict"]


def test_base_ledger_and_parameter_grid_mutation_changes_hash(tmp_path):
    ledger = tmp_path / "ledger.csv"
    grid = tmp_path / "grid.csv"
    shutil.copy2(oracle.LEDGER, ledger)
    shutil.copy2(oracle.PARAM_GRID, grid)
    ledger_before = oracle.sha256_file(ledger)
    grid_before = oracle.sha256_file(grid)
    ledger.write_text(ledger.read_text() + "\n")
    grid.write_text(grid.read_text() + "\n")

    assert oracle.sha256_file(ledger) != ledger_before
    assert oracle.sha256_file(grid) != grid_before
