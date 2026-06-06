from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.agents.trade_quality_truth_audit import analyze_trade_quality_truth, build_trade_quality_truth_audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _report(source_texts: dict[str, str], runtime_payloads: dict[str, object] | None = None) -> dict[str, object]:
    return analyze_trade_quality_truth(
        repo_root=REPO_ROOT,
        source_texts=source_texts,
        runtime_payloads=runtime_payloads or {},
    )


def test_trade_quality_truth_audit_flags_are_read_only() -> None:
    report = _report({})

    assert report["read_only"] is True
    assert report["broker_api_called"] is False
    assert report["is_order_action"] is False
    assert report["live_order_allowed"] is False
    assert report["runtime_mutation_allowed"] is False


def test_fallback_executable_detector_blocks_executable_fallback_row() -> None:
    runtime_payloads = {
        "top_opportunities": {
            "payload": {
                "top_executable_opportunities": [
                    {
                        "trade_id": "FALLBACK-1",
                        "symbol": "NIFTY",
                        "fallback_candidate": True,
                        "recovered_fallback": True,
                        "execution_status": "executable",
                        "final_action": "EXECUTE",
                        "readiness": "READY",
                        "visibility_bucket": "executable",
                        "executable_candidate": True,
                        "reportable_executable": True,
                        "confidence_raw": 0.88,
                    }
                ],
                "top_advisory_opportunities": [],
                "top_blocked_opportunities": [],
                "top_executable_count": 1,
                "top_advisory_count": 0,
                "top_blocked_count": 0,
                "selector_outcome": "EXECUTABLE",
            }
        }
    }
    report = _report({}, runtime_payloads)

    assert report["fallback_executable"]["verdict"] == "BLOCKER"
    assert report["fallback_executable"]["can_fallback_be_executable"] is True
    assert report["fallback_executable"]["confidence"] == "HIGH"


def test_fallback_advisory_row_does_not_become_executable_blocker() -> None:
    runtime_payloads = {
        "top_opportunities": {
            "payload": {
                "top_executable_opportunities": [],
                "top_advisory_opportunities": [
                    {
                        "trade_id": "FALLBACK-2",
                        "symbol": "BANKNIFTY",
                        "fallback_candidate": True,
                        "recovered_fallback": True,
                        "execution_status": "advisory_only",
                        "final_action": "ADVISORY_ONLY",
                        "readiness": "ADVISORY_ONLY",
                        "visibility_bucket": "advisory",
                        "executable_candidate": False,
                        "reportable_executable": False,
                        "confidence_raw": 0.31,
                    }
                ],
                "top_blocked_opportunities": [],
                "top_executable_count": 0,
                "top_advisory_count": 1,
                "top_blocked_count": 0,
                "selector_outcome": "ADVISORY_ONLY",
            }
        }
    }
    report = _report({}, runtime_payloads)

    assert report["fallback_executable"]["verdict"] == "PASS"
    assert report["fallback_executable"]["can_fallback_be_executable"] is False


def test_confidence_component_detector_finds_missing_and_present_components() -> None:
    scoring_source = (REPO_ROOT / "core" / "candidate_scoring.py").read_text(encoding="utf-8")
    missing_sources = {
        "core/candidate_scoring.py": scoring_source.replace("liquidity_score", "liquidity_metric").replace("spread_score", "spread_metric").replace("timing_score", "timing_metric").replace("OPTION_LTP_SLA_SEC", "OPTION_LTP_SLA_WINDOW")
    }
    missing_report = _report(missing_sources)
    missing_confidence = missing_report["confidence_truth"]
    assert missing_confidence["verdict"] == "PASS"
    assert missing_confidence["uses_liquidity"] is False
    assert missing_confidence["uses_spread"] is False
    assert missing_confidence["uses_freshness"] is False
    assert missing_confidence["uses_regime"] is True
    assert missing_confidence["uses_fallback_penalty"] is False
    assert missing_confidence["confidence_raw_locations"]
    assert missing_confidence["confidence_raw_locations"][0].startswith("core/candidate_scoring.py:")

    present_sources = {"core/candidate_scoring.py": scoring_source}
    present_report = _report(present_sources)
    present_confidence = present_report["confidence_truth"]
    assert present_confidence["verdict"] == "PASS"
    assert present_confidence["uses_liquidity"] is True
    assert present_confidence["uses_spread"] is True
    assert present_confidence["uses_freshness"] is True
    assert present_confidence["uses_regime"] is True
    assert present_confidence["uses_fallback_penalty"] is False
    assert present_confidence["confidence_raw_locations"]
    assert present_confidence["confidence_raw_locations"][0].startswith("core/candidate_scoring.py:")


def test_ranking_truth_detector_distinguishes_true_ranking_from_filter_only() -> None:
    filter_only_sources = {
        "dashboard/streamlit_app_runtime.py": (
            "st.caption(\"Main table shows engine-ranked opportunities from persisted top-opportunity snapshots.\")\n"
            "suggested_df = select_display_df(suggested_df, \"advisory\")\n"
            "st.caption(\"Advisory / Fallback\")\n"
        )
    }
    filter_only_report = _report(filter_only_sources)
    assert filter_only_report["ranking_truth"]["ranking_type"] == "filter_only"
    assert filter_only_report["ranking_truth"]["verdict"] == "WARN"

    true_ranking_sources = {
        "core/candidate_ranking.py": (
            "ranked_inputs = sorted(\n"
            "    records,\n"
            "    key=lambda record: _sort_key(record, _directional_warnings(record, directional_flags)),\n"
            ")\n"
            "score_eligibility = _rank_score_eligibility(record, feed_risk_suppressed)\n"
            "final_score = record.final_score\n"
            "feed_risk_suppression = _should_suppress_for_feed_risk(record)\n"
        )
    }
    ranked_report = _report(true_ranking_sources)
    assert ranked_report["ranking_truth"]["ranking_type"] == "true_ranking"
    assert ranked_report["ranking_truth"]["verdict"] == "PASS"


def test_candidate_pool_detector_distinguishes_pool_from_direct_emit_path() -> None:
    direct_emit_sources = {
        "strategies/trade_builder.py": (
            "def build(self):\n"
            "    emit_trade(trade)\n"
            "    candidate_created = True\n"
        )
    }
    direct_emit_report = _report(direct_emit_sources)
    assert direct_emit_report["candidate_pool_truth"]["has_candidate_pool"] is False
    assert direct_emit_report["candidate_pool_truth"]["direct_emit_paths"] == ["strategies/trade_builder.py"]
    assert direct_emit_report["candidate_pool_truth"]["verdict"] == "WARN"

    candidate_pool_sources = {
        "core/candidate_pool.py": (
            "class CandidatePool:\n"
            "    def summary(self):\n"
            "        return {'executable_eligible_count': 1}\n"
        ),
        "core/strategy_candidate_pool.py": (
            "class StrategyCandidatePoolReport:\n"
            "    def build_strategy_candidate_pool(self):\n"
            "        return {'does_not_rank_candidates': True}\n"
        ),
    }
    candidate_pool_report = _report(candidate_pool_sources)
    assert candidate_pool_report["candidate_pool_truth"]["has_candidate_pool"] is True
    assert candidate_pool_report["candidate_pool_truth"]["verdict"] == "PASS"


def test_script_runs_without_runtime_logs_and_writes_reports(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "workdir"
    runtime_dir = workdir / ".runtime"
    logs_dir = workdir / "logs"
    out_dir = workdir / ".runtime" / "trade_quality_audit"
    runtime_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    monkeypatch.chdir(workdir)

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_trade_quality_truth_audit.py"),
            "--repo-root",
            str(REPO_ROOT),
            "--runtime-dir",
            str(runtime_dir),
            "--logs-dir",
            str(logs_dir),
            "--out-dir",
            str(out_dir),
            "--format",
            "both",
            "--copy-latest",
            "true",
        ],
        cwd=workdir,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    json_report = out_dir / "trade_quality_truth_audit_latest.json"
    md_report = out_dir / "trade_quality_truth_audit_latest.md"
    latest_copy_json = workdir / ".runtime" / "agent_reports" / "trade_quality_truth_audit_latest.json"
    latest_copy_md = workdir / ".runtime" / "agent_reports" / "trade_quality_truth_audit_latest.md"
    assert json_report.exists(), json_report
    assert md_report.exists(), md_report
    assert latest_copy_json.exists(), latest_copy_json
    assert latest_copy_md.exists(), latest_copy_md
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["read_only"] is True
    assert payload["broker_api_called"] is False
    assert payload["is_order_action"] is False
    assert payload["live_order_allowed"] is False
    assert payload["runtime_mutation_allowed"] is False
    assert "# Trade Quality Truth Audit" in md_report.read_text(encoding="utf-8")


def test_builder_respects_format_json_and_markdown(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "format-workdir"
    runtime_dir = workdir / ".runtime"
    logs_dir = workdir / "logs"
    runtime_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    monkeypatch.chdir(workdir)

    json_only_dir = workdir / "json-only"
    report_json = build_trade_quality_truth_audit(
        repo_root=REPO_ROOT,
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        out_dir=json_only_dir,
        format="json",
        copy_latest=False,
    )
    assert report_json.read_only is True
    assert (json_only_dir / "trade_quality_truth_audit_latest.json").exists()
    assert not (json_only_dir / "trade_quality_truth_audit_latest.md").exists()

    markdown_only_dir = workdir / "markdown-only"
    report_md = build_trade_quality_truth_audit(
        repo_root=REPO_ROOT,
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        out_dir=markdown_only_dir,
        format="markdown",
        copy_latest=False,
    )
    assert report_md.read_only is True
    assert not (markdown_only_dir / "trade_quality_truth_audit_latest.json").exists()
    assert (markdown_only_dir / "trade_quality_truth_audit_latest.md").exists()
