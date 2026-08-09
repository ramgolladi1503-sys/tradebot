import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "research" / "hypothesis_factory"


def load_module(name: str):
    path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


candidate_report = load_module("build_candidate_filter_report")
robustness = load_module("run_robustness")
certifier = load_module("certify_strategy_candidate")


def write_screen_run(run_dir: Path, rows: list[dict[str, object]]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({
            "run_id": "SCREEN-TEST",
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
            "certification": "NOT_CERTIFIED",
            "loaded_rows": 1000,
        }),
        encoding="utf-8",
    )
    keys = sorted({key for row in rows for key in row.keys()})
    with (run_dir / "leaderboard.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def base_candidate(**updates):
    row = {
        "hypothesis_id": "HYP-A",
        "instrument": "BANKNIFTY",
        "family": "opening_range_failure",
        "direction": "BUY_PE",
        "window_minutes": "5",
        "filters": "['spread_ok', 'volume_spike']",
        "exit_rule": "time_stop",
        "trades": "120",
        "sessions_traded": "24",
        "top_session_trade_share": "0.10",
        "top_session_abs_pnl_share": "0.20",
        "win_rate": "0.55",
        "net_expectancy_bps": "4.0",
        "profit_factor": "1.4",
        "max_drawdown_bps": "-120.0",
        "fallback_execution_data_used": "False",
        "broker_actions_allowed": "False",
        "runtime_authority": "NONE",
        "score": "1.0",
        "certification": "NOT_CERTIFIED",
        "status": "PROMISING_NOT_CERTIFIED",
    }
    row.update(updates)
    return row


def test_candidate_filter_report_collapses_duplicate_shapes(tmp_path):
    run_dir = tmp_path / "screen"
    write_screen_run(run_dir, [
        base_candidate(hypothesis_id="HYP-A", score="2.0"),
        base_candidate(hypothesis_id="HYP-B", score="1.0"),
    ])

    args = candidate_report.build_parser().parse_args([
        "--screen-run-dir", str(run_dir),
        "--min-trades", "20",
    ])
    report = candidate_report.build_report(args)

    assert report["summary"]["candidates"] == 2
    assert report["summary"]["unique_shapes"] == 1
    assert report["summary"]["duplicates"] == 1
    assert report["summary"]["eligible_for_robustness"] == 1
    duplicate = [row for row in report["candidates"] if row["duplicate_shape"]][0]
    assert "duplicate_shape" in duplicate["rejection_reasons"]
    assert report["runtime_authority"] == "NONE"
    assert report["broker_actions_allowed"] is False


def test_missing_session_breadth_metrics_fail_closed(tmp_path):
    run_dir = tmp_path / "screen"
    candidate = base_candidate(
        hypothesis_id="HYP-NO-BREADTH",
        sessions_traded="",
        top_session_trade_share="",
        top_session_abs_pnl_share="",
    )
    write_screen_run(run_dir, [candidate])

    report = candidate_report.build_report(
        candidate_report.build_parser().parse_args([
            "--screen-run-dir", str(run_dir),
            "--min-trades", "20",
        ])
    )

    assert report["summary"]["eligible_for_robustness"] == 0
    reasons = report["candidates"][0]["rejection_reasons"]
    assert "sessions_traded_below_threshold" in reasons


def test_low_trade_candidate_cannot_certify_even_with_missing_robustness(tmp_path):
    run_dir = tmp_path / "screen"
    write_screen_run(run_dir, [base_candidate(hypothesis_id="HYP-LOW", trades="6")])
    filter_report = candidate_report.build_report(
        candidate_report.build_parser().parse_args([
            "--screen-run-dir", str(run_dir),
            "--min-trades", "20",
        ])
    )

    out_dir = tmp_path / "cert"
    result = certifier.certify(
        certifier.build_parser().parse_args([
            "--screen-run-dir", str(run_dir),
            "--candidate-filter-report", str(run_dir / "candidate_filter_report.json"),
            "--candidate-hypothesis-id", "HYP-LOW",
            "--output-dir", str(out_dir),
        ])
    )

    assert filter_report["summary"]["eligible_for_robustness"] == 0
    assert result["decision"]["verdict"] == "REJECTED"
    assert "trades_below_threshold" in result["decision"]["blocking_reasons"]
    assert result["decision"]["runtime_authority"] == "NONE"
    assert result["decision"]["broker_actions_allowed"] is False


def test_missing_trade_ledger_blocks_robustness(tmp_path):
    run_dir = tmp_path / "screen"
    write_screen_run(run_dir, [base_candidate()])
    candidate_report.build_report(
        candidate_report.build_parser().parse_args(["--screen-run-dir", str(run_dir)])
    )

    result = robustness.run(
        robustness.build_parser().parse_args([
            "--screen-run-dir", str(run_dir),
            "--candidate-hypothesis-id", "HYP-A",
            "--output-dir", str(tmp_path / "robust"),
            "--run-id", "ROBUST-MISSING",
        ])
    )

    assert result["status"] == "ROBUSTNESS_BLOCKED"
    assert result["robustness_passed"] is False
    assert "missing_trade_ledger" in result["blocking_reasons"]
    assert result["runtime_authority"] == "NONE"
    assert result["broker_actions_allowed"] is False


def test_synthetic_passed_robustness_can_validate_research_only(tmp_path):
    run_dir = tmp_path / "screen"
    candidate = base_candidate(hypothesis_id="HYP-PASS", trades="150", net_expectancy_bps="6.0")
    write_screen_run(run_dir, [candidate])
    candidate_filter = candidate_report.build_report(
        candidate_report.build_parser().parse_args([
            "--screen-run-dir", str(run_dir),
            "--min-trades", "100",
            "--min-profit-factor", "1.01",
        ])
    )
    shape_key = candidate_filter["candidates"][0]["candidate_shape_key"]
    assert candidate_filter["candidates"][0]["eligible_for_robustness"] is True

    trade_path = run_dir / "candidate_trades.csv"
    with trade_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "timestamp",
            "session",
            "hypothesis_id",
            "candidate_shape_key",
            "pnl_bps",
            "is_fallback",
        ])
        writer.writeheader()
        for index in range(150):
            session = f"2026-01-{1 + index // 10:02d}"
            writer.writerow({
                "timestamp": f"{session}T09:{15 + index % 10:02d}:00",
                "session": session,
                "hypothesis_id": "HYP-PASS",
                "candidate_shape_key": shape_key,
                "pnl_bps": "6.0" if index % 5 else "2.0",
                "is_fallback": "false",
            })

    robustness_result = robustness.run(
        robustness.build_parser().parse_args([
            "--screen-run-dir", str(run_dir),
            "--candidate-filter-report", str(run_dir / "candidate_filter_report.json"),
            "--candidate-hypothesis-id", "HYP-PASS",
            "--candidate-shape-key", shape_key,
            "--trades-csv", str(trade_path),
            "--output-dir", str(tmp_path / "robust"),
            "--run-id", "ROBUST-PASS",
            "--min-trades", "100",
            "--cost-stress-bps", "0",
            "--cost-stress-bps", "1",
            "--negative-control-iterations", "50",
        ])
    )
    assert robustness_result["status"] == "ROBUSTNESS_PASSED"

    result = certifier.certify(
        certifier.build_parser().parse_args([
            "--screen-run-dir", str(run_dir),
            "--candidate-filter-report", str(run_dir / "candidate_filter_report.json"),
            "--robustness-run-dir", str(tmp_path / "robust" / "ROBUST-PASS"),
            "--candidate-hypothesis-id", "HYP-PASS",
            "--candidate-shape-key", shape_key,
            "--output-dir", str(tmp_path / "cert"),
        ])
    )

    assert result["decision"]["verdict"] == "VALIDATED_RESEARCH"
    assert result["integration"]["allowed_tradebot_mode"] == "VALIDATED_RESEARCH"
    assert result["integration"]["runtime_authority"] == "NONE"
    assert result["integration"]["broker_actions_allowed"] is False
    passport = json.loads((tmp_path / "cert" / "strategy_passport.json").read_text(encoding="utf-8"))
    assert passport["runtime_authority"] == "NONE"
    assert passport["broker_actions_allowed"] is False
    assert passport["evidence_hashes"]
