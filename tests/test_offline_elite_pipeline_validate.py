from __future__ import annotations

import json

from scripts.offline_elite_pipeline_validate import main, run_offline_pipeline


def _candidate(**overrides):
    row = {
        "trade_id": "T-OFFLINE",
        "symbol": "NIFTY",
        "strategy": "offline_unit",
        "strategy_family": "offline_unit",
        "direction_family": "bullish",
        "confidence": 0.8,
        "rank_score": 0.8,
        "final_score": 0.8,
        "opt_ltp": 120.0,
        "current_ltp": 120.0,
        "best_bid": 119.8,
        "best_ask": 120.2,
        "spread_pct": 0.003,
        "liquidity_score": 0.82,
        "quote_age_sec": 0.3,
        "max_quote_age_sec": 2.0,
        "quote_source": "live_broker",
        "spread_source": "live_book",
        "liquidity_source": "live_book",
        "contract_exact_match": True,
        "execution_entry": 120.2,
        "entry_price": 120.2,
        "stop_loss": 110.0,
        "target": 145.0,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "candidate_status": "executable",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
        "tradable": True,
        "capital_at_risk": 120.2,
        "size_mult": 1.0,
    }
    row.update(overrides)
    return row


def test_offline_pipeline_allows_clean_candidate_and_blocks_dirty_candidate():
    payload = run_offline_pipeline(
        [
            _candidate(trade_id="T-CLEAN"),
            _candidate(
                trade_id="T-DIRTY",
                phase2_spread_fallback_used=True,
                spread_source="fallback_default",
            ),
        ]
    )

    assert payload["summary"]["total_candidates"] == 2
    assert payload["summary"]["pipeline_passed"] == 1
    assert payload["summary"]["data_truth_blocked"] == 1
    assert payload["summary"]["dirty_capital_violations"] == 0
    by_ref = {row["ref"]: row for row in payload["stages"]}
    assert by_ref["T-CLEAN"]["capital_assigned"] > 0
    assert by_ref["T-DIRTY"]["capital_assigned"] == 0.0
    assert "fallback_spread" in by_ref["T-DIRTY"]["execution_truth_blockers"]


def test_offline_pipeline_cli_writes_report(tmp_path):
    source = tmp_path / "candidates.json"
    source.write_text(
        json.dumps(
            [
                _candidate(trade_id="T-CLEAN"),
                _candidate(trade_id="T-UNKNOWN", quote_source="unknown"),
            ]
        ),
        encoding="utf-8",
    )
    out_json = tmp_path / "offline.json"
    out_md = tmp_path / "offline.md"

    code = main(
        [
            "--inputs",
            str(source),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--fail-on-dirty-capital",
        ]
    )

    assert code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["dirty_capital_violations"] == 0
    assert payload["summary"]["data_truth_blocked"] == 1
    assert "Offline Elite Pipeline Validation Report" in out_md.read_text(encoding="utf-8")
