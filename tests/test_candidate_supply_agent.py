from __future__ import annotations

import json
from pathlib import Path

from core.agents.candidate_supply_agent import analyze_candidate_supply


def test_candidate_supply_agent_flags_empty_supply(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 0, "phase2_input_candidate_count": 0, "top_blockers": {"RISK_HALT": 1}}),
        encoding="utf-8",
    )

    report = analyze_candidate_supply(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["metrics"]["raw_candidate_count"] == 0
    assert payload["read_only"] is True
    assert payload["no_order_action"] is True


def test_candidate_supply_agent_attribues_zero_supply_to_strategy_qualification_and_latency_and_slo(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps(
            {
                "raw_candidate_count": 0,
                "real_candidate_count": 0,
                "phase2_input_candidate_count": 0,
                "feed_was_fresh_before_candidate_supply_zero": True,
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "strategy_no_qualified_reasons_latest.json").write_text(
        json.dumps(
            {
                "strategy_no_qualified_applicable": True,
                "no_candidate_constructed": True,
                "gate_reasons": {"NO_STRATEGY_QUALIFIED": 1},
                "by_symbol": {
                    "NIFTY": {
                        "attempt_count": 1,
                        "strategies_attempted": ["MEAN_REVERT"],
                        "trade_builder_ran": True,
                        "candidate_produced_count": 0,
                        "candidate_generated_then_dropped_count": 0,
                        "no_setup_qualified_count": 1,
                        "reason_categories": {"direction_or_regime_mismatch": 1},
                        "attempts": [
                            {
                                "symbol": "NIFTY",
                                "strategy_id": "MEAN_REVERT",
                                "trade_builder_reached": True,
                                "no_candidate_constructed": True,
                                "no_setup_reason": "regime_low_confidence",
                                "reason_category": "direction_or_regime_mismatch",
                                "strategy_blocker_stage": "N8_STRATEGY_SELECT",
                                "strategy_blocker_reasons": [
                                    "NO_STRATEGY_QUALIFIED",
                                    "cross_asset_optional_stale",
                                    "regime_unstable_debounced:1/2",
                                    "regime_low_confidence",
                                ],
                                "candidate_family_considered": None,
                                "picked_candidate_family": None,
                                "regime_confidence": 0.17,
                                "regime_entropy": 0.88,
                                "regime_unstable_debounced": True,
                            }
                        ],
                    }
                },
                "latency_guard": {
                    "latency_guard_triggered": True,
                    "latency_guard_action": "cooldown",
                    "latency_guard_reason": "latency_guard_prebuild_skip",
                },
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                "ts_epoch=1500.0 boot_epoch=1000.0 run_id=run-old event=FEED_REBALANCE_APPLIED subscribe_count=12 unsubscribe_count=11",
                "ts_epoch=1500.5 boot_epoch=1000.0 run_id=run-old event=CONNECTION_ERROR code=1006",
                "ts_epoch=1501.0 boot_epoch=1000.0 run_id=run-old event=FEED_LTP_STALE symbol=NIFTY",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "run_id": "run-current",
                "boot_epoch": 2000.0,
                "ts_epoch": 2003.5,
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}},
                "gate_status": {"N2_FEED_FRESH": {"ok": True}},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_candidate_supply(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["metrics"]["raw_candidate_count"] == 0
    assert payload["metrics"]["feed_was_fresh_before_candidate_supply_zero"] is True
    assert payload["metrics"]["candidate_supply_evidence_scope"] == "mixed"
    assert payload["metrics"]["feed_churn_evidence_scope"] == "historical_tail"
    assert payload["metrics"]["first_candidate_supply_zero_subtype"] == "CANDIDATE_SUPPLY_ZERO_STRATEGY_QUALIFICATION"
    assert "CANDIDATE_SUPPLY_ZERO_REGIME_UNSTABLE" in payload["metrics"]["candidate_supply_zero_subtypes"]
    assert "CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_COOLDOWN" in payload["metrics"]["candidate_supply_zero_subtypes"]
    assert "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE" in payload["metrics"]["candidate_supply_zero_subtypes"]
    assert payload["metrics"]["trade_builder_reached"] is True
    assert payload["metrics"]["no_candidate_constructed"] is True
    assert payload["metrics"]["candidate_family_considered"] is None
    assert payload["metrics"]["picked_candidate_family"] is None


def test_candidate_supply_agent_keeps_strategy_qualification_first_when_latency_is_secondary(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 0, "phase2_input_candidate_count": 0}),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "strategy_no_qualified_reasons_latest.json").write_text(
        json.dumps(
            {
                "strategy_no_qualified_applicable": True,
                "no_candidate_constructed": True,
                "gate_reasons": {"NO_STRATEGY_QUALIFIED": 1},
                "by_symbol": {
                    "NIFTY": {
                        "attempts": [
                            {
                                "symbol": "NIFTY",
                                "strategy_blocker_stage": "N8_STRATEGY_SELECT",
                                "strategy_blocker_reasons": ["NO_STRATEGY_QUALIFIED", "regime_low_confidence"],
                                "reason_category": "direction_or_regime_mismatch",
                                "trade_builder_reached": True,
                                "no_candidate_constructed": True,
                                "candidate_family_considered": None,
                                "picked_candidate_family": None,
                                "regime_confidence": 0.12,
                                "regime_entropy": 0.91,
                                "regime_unstable_debounced": True,
                            }
                        ]
                    }
                },
                "latency_guard": {
                    "latency_guard_triggered": True,
                    "latency_guard_action": "cooldown",
                    "latency_guard_reason": "latency_guard_prebuild_skip",
                },
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps({"ws_connected": True, "runtime_state": "RUNNING", "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}}, "gate_status": {"N2_FEED_FRESH": {"ok": True}}}),
        encoding="utf-8",
    )

    payload = analyze_candidate_supply(runtime_dir=runtime_dir, logs_dir=logs_dir).to_dict()
    assert payload["metrics"]["first_candidate_supply_zero_subtype"] == "CANDIDATE_SUPPLY_ZERO_STRATEGY_QUALIFICATION"
    assert payload["metrics"]["candidate_supply_zero_timeline"][0]["primary_subtype"] == "CANDIDATE_SUPPLY_ZERO_STRATEGY_QUALIFICATION"
    assert any(
        item["primary_subtype"] == "CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_COOLDOWN"
        for item in payload["metrics"]["candidate_supply_zero_timeline"]
    )


def test_candidate_supply_agent_marks_degrade_exit_only_subtype(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 0, "phase2_input_candidate_count": 0}),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "strategy_no_qualified_reasons_latest.json").write_text(
        json.dumps(
            {
                "strategy_no_qualified_applicable": True,
                "no_candidate_constructed": True,
                "gate_reasons": {"NO_STRATEGY_QUALIFIED": 1},
                "latency_guard": {
                    "latency_guard_triggered": True,
                    "latency_guard_action": "degrade_exit_only",
                    "latency_guard_reason": "latency_guard_prebuild_skip",
                },
                "by_symbol": {},
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps({"ws_connected": True, "runtime_state": "RUNNING", "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}}, "gate_status": {"N2_FEED_FRESH": {"ok": True}}}),
        encoding="utf-8",
    )

    payload = analyze_candidate_supply(runtime_dir=runtime_dir, logs_dir=logs_dir).to_dict()
    assert "CANDIDATE_SUPPLY_ZERO_LATENCY_GUARD_DEGRADE_EXIT_ONLY" in payload["metrics"]["candidate_supply_zero_subtypes"]


def test_candidate_supply_agent_marks_slo_feed_stale_subtype(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 0, "phase2_input_candidate_count": 0}),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "ts_epoch=1501.0 boot_epoch=1000.0 run_id=run-old event=FEED_LTP_STALE symbol=NIFTY\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps({"run_id": "run-current", "boot_epoch": 2000.0, "ws_connected": True, "runtime_state": "RUNNING", "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}}, "gate_status": {"N2_FEED_FRESH": {"ok": True}}}),
        encoding="utf-8",
    )

    payload = analyze_candidate_supply(runtime_dir=runtime_dir, logs_dir=logs_dir).to_dict()
    assert payload["metrics"]["first_candidate_supply_zero_subtype"] == "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE"
    assert "CANDIDATE_SUPPLY_ZERO_SLO_FEED_STALE" in payload["metrics"]["candidate_supply_zero_subtypes"]
