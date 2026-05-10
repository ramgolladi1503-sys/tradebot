from __future__ import annotations

import json

from scripts.run_shadow_truth_audit import main


def test_shadow_truth_audit_runner_writes_shadow_only_reports(tmp_path):
    source = tmp_path / "queue.json"
    out_json = tmp_path / "shadow.json"
    out_md = tmp_path / "shadow.md"
    source.write_text(
        json.dumps(
            [
                {
                    "trade_id": "T-CLEAN",
                    "symbol": "NIFTY",
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
                    "execution_entry_status": "executable",
                    "execution_entry_source": "ask",
                    "execution_allowed": True,
                    "eligible_for_execution": True,
                    "selected_for_execution": True,
                },
                {
                    "trade_id": "T-DIRTY",
                    "symbol": "BANKNIFTY",
                    "opt_ltp": 220.0,
                    "current_ltp": 220.0,
                    "best_bid": 219.8,
                    "best_ask": 220.2,
                    "spread_pct": 0.003,
                    "liquidity_score": 0.82,
                    "quote_age_sec": 0.3,
                    "max_quote_age_sec": 2.0,
                    "quote_source": "live_broker",
                    "spread_source": "fallback_default",
                    "liquidity_source": "live_book",
                    "phase2_spread_fallback_used": True,
                    "contract_exact_match": True,
                    "execution_entry": 220.2,
                    "execution_entry_status": "executable",
                    "execution_entry_source": "ask",
                    "execution_allowed": True,
                    "eligible_for_execution": True,
                    "selected_for_execution": True,
                },
            ]
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--inputs",
            str(source),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ]
    )

    assert code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["mode"] == "SHADOW_ONLY"
    assert payload["behavior_changed"] is False
    assert payload["severity_counts"]["CRITICAL"] == 1
    assert "Shadow Truth Audit Report" in out_md.read_text(encoding="utf-8")


def test_shadow_truth_audit_runner_can_fail_on_critical(tmp_path):
    source = tmp_path / "queue.json"
    source.write_text(
        json.dumps(
            [
                {
                    "trade_id": "T-DIRTY",
                    "symbol": "NIFTY",
                    "opt_ltp": 120.0,
                    "current_ltp": 120.0,
                    "best_bid": 119.8,
                    "best_ask": 120.2,
                    "spread_pct": 0.003,
                    "liquidity_score": 0.82,
                    "quote_age_sec": 0.3,
                    "max_quote_age_sec": 2.0,
                    "quote_source": "unknown",
                    "spread_source": "live_book",
                    "liquidity_source": "live_book",
                    "contract_exact_match": True,
                    "execution_entry": 120.2,
                    "execution_entry_status": "executable",
                    "execution_entry_source": "ask",
                    "execution_allowed": True,
                    "eligible_for_execution": True,
                    "selected_for_execution": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--inputs",
            str(source),
            "--out-json",
            str(tmp_path / "shadow.json"),
            "--out-md",
            str(tmp_path / "shadow.md"),
            "--fail-on-critical",
        ]
    )

    assert code == 1
