from __future__ import annotations

import json

from dashboard.metrics_runtime import load_runtime_metrics


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def test_runtime_metrics_aggregates_counts_from_runtime_logs(tmp_path):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    desk_logs = logs_root / "desks" / "DEFAULT"
    observability_root = runtime_root / "observability"

    _write_jsonl(
        desk_logs / "candidates.jsonl",
        [
            {
                "candidate_id": "cand-1",
                "cycle_id": "cycle-a",
                "symbol": "NIFTY",
                "strategy_id": "BREAKOUT",
                "ts_epoch": 1_710_000_000.0,
            },
            {
                "candidate_id": "cand-2",
                "cycle_id": "cycle-a",
                "symbol": "NIFTY",
                "strategy_id": "BREAKOUT",
                "ts_epoch": 1_710_000_000.0,
            },
            {
                "candidate_id": "cand-3",
                "cycle_id": "cycle-b",
                "symbol": "BANKNIFTY",
                "strategy_id": "PULLBACK",
                "ts_epoch": 1_710_000_060.0,
            },
        ],
    )
    _write_jsonl(
        observability_root / "trade_lifecycle.jsonl",
        [
            {
                "trade_id": "T-1",
                "symbol": "NIFTY",
                "strategy": "BREAKOUT",
                "stage": "candidate_generation",
                "status": "created",
                "reason": "builder",
                "timestamp": "2026-03-19T14:00:00+00:00",
                "schema_version": 1,
            },
            {
                "trade_id": "T-1",
                "symbol": "NIFTY",
                "strategy": "BREAKOUT",
                "stage": "scoring_ranking",
                "status": "selected",
                "reason": "top_rank",
                "timestamp": "2026-03-19T14:00:05+00:00",
                "schema_version": 1,
            },
            {
                "trade_id": "T-1",
                "symbol": "NIFTY",
                "strategy": "BREAKOUT",
                "stage": "execution_feasibility",
                "status": "non_executable",
                "reason": "bidask_missing",
                "timestamp": "2026-03-19T14:00:06+00:00",
                "schema_version": 1,
            },
            {
                "trade_id": "T-1",
                "symbol": "NIFTY",
                "strategy": "BREAKOUT",
                "stage": "execution_feasibility",
                "status": "executable",
                "reason": "ask_live",
                "timestamp": "2026-03-19T14:00:08+00:00",
                "schema_version": 1,
            },
            {
                "trade_id": "T-2",
                "symbol": "BANKNIFTY",
                "strategy": "PULLBACK",
                "stage": "candidate_generation",
                "status": "created",
                "reason": "builder",
                "timestamp": "2026-03-19T14:00:10+00:00",
                "schema_version": 1,
            },
            {
                "trade_id": "T-2",
                "symbol": "BANKNIFTY",
                "strategy": "PULLBACK",
                "stage": "scoring_ranking",
                "status": "skipped",
                "reason": "not_selected_for_execution",
                "timestamp": "2026-03-19T14:00:12+00:00",
                "schema_version": 1,
            },
        ],
    )
    _write_jsonl(
        logs_root / "rejected_candidates.jsonl",
        [
            {
                "trade_id": "T-3",
                "reject_reason": "spread_too_wide",
                "blockers": ["spread_too_wide"],
                "warnings": ["depth_missing"],
                "opportunity_score": 0.32,
            }
        ],
    )
    _write_jsonl(
        logs_root / "suggestions.jsonl",
        [
            {
                "trade_id": "T-1",
                "execution_status": "executable",
                "readiness": "READY",
                "final_action": "EXECUTE",
                "strategy": "BREAKOUT",
                "opportunity_score": 0.82,
                "allocation_reason": "allocated",
                "slot_id": "slot-1",
                "capital_assigned": 12000.0,
                "blockers": [],
            },
            {
                "trade_id": "T-2",
                "execution_status": "advisory_only",
                "readiness": "ADVISORY_ONLY",
                "final_action": "ADVISORY_ONLY",
                "strategy": "PULLBACK",
                "opportunity_score": 0.61,
                "allocation_reason": "deferred_per_theme_cap",
                "blockers": ["theme_cap"],
                "hard_blockers": [],
                "warnings": ["spread_warning"],
            },
        ],
    )
    (logs_root / "review_queue.json").write_text("[]", encoding="utf-8")
    (observability_root / "pipeline_funnel.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-03-19T14:00:12+00:00",
                "schema_version": 1,
                "universe": 2,
                "candidates": 3,
                "scored": 2,
                "ready": 1,
                "executable": 1,
                "emitted": 2,
            }
        ),
        encoding="utf-8",
    )
    (runtime_root / "top_opportunities_latest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-03-19T14:00:12+00:00",
                "producer": "test",
                "payload": {
                    "top_executable_opportunities": [],
                    "top_advisory_opportunities": [
                        {
                            "trade_id": "T-2",
                            "allocation_reason": "deferred_per_theme_cap",
                            "selected_for_execution": False,
                            "opportunity_score": 0.61,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    metrics = load_runtime_metrics(
        desk_id="DEFAULT",
        max_rows=200,
        cycle_limit=10,
        paths={
            "pipeline_funnel": observability_root / "pipeline_funnel.json",
            "trade_lifecycle": observability_root / "trade_lifecycle.jsonl",
            "candidates_stream": desk_logs / "candidates.jsonl",
            "decisions_stream": desk_logs / "decisions.jsonl",
            "decision_scan_summary": logs_root / "decision_scan_summary.jsonl",
            "suggestions": logs_root / "suggestions.jsonl",
            "rejected_candidates": logs_root / "rejected_candidates.jsonl",
            "review_queue": logs_root / "review_queue.json",
            "top_opportunities": runtime_root / "top_opportunities_latest.json",
        },
    )

    assert metrics["summary"]["candidate_pool_latest"] == 1
    assert metrics["summary"]["ranked_candidate_count"] == 2
    assert metrics["summary"]["top_strategy_by_candidate_volume"] == {"strategy": "BREAKOUT", "count": 2}
    assert metrics["summary"]["advisory_conversion_method"] == "lifecycle_transition"
    assert metrics["summary"]["advisory_conversion_numerator"] == 1
    assert metrics["summary"]["advisory_conversion_denominator"] == 1
    assert metrics["candidate_pool_by_cycle"] == [
        {"cycle": "cycle-a", "candidate_pool_size": 2, "ts_epoch": 1710000000.0},
        {"cycle": "cycle-b", "candidate_pool_size": 1, "ts_epoch": 1710000060.0},
    ]
    assert metrics["rejection_reason_distribution"][0] == {"reason": "spread_too_wide", "count": 1}
    assert {row["bucket"]: row["count"] for row in metrics["score_distribution"]} == {"0.2-0.4": 1, "0.6-0.8": 1, "0.8-1.0": 1}
    assert metrics["allocation_summary"]["accepted_count"] == 1
    assert metrics["allocation_summary"]["rejected_count"] == 1
    assert metrics["allocation_summary"]["reason_distribution"][0] == {"reason": "allocated", "count": 1}
    assert any(row["blocker"] == "theme_cap" for row in metrics["blockers_distribution"])


def test_runtime_metrics_missing_logs_degrade_gracefully(tmp_path):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    metrics = load_runtime_metrics(
        desk_id="DEFAULT",
        max_rows=100,
        cycle_limit=5,
        paths={
            "pipeline_funnel": runtime_root / "observability" / "pipeline_funnel.json",
            "trade_lifecycle": runtime_root / "observability" / "trade_lifecycle.jsonl",
            "candidates_stream": logs_root / "desks" / "DEFAULT" / "candidates.jsonl",
            "decisions_stream": logs_root / "desks" / "DEFAULT" / "decisions.jsonl",
            "decision_scan_summary": logs_root / "decision_scan_summary.jsonl",
            "suggestions": logs_root / "suggestions.jsonl",
            "rejected_candidates": logs_root / "rejected_candidates.jsonl",
            "review_queue": logs_root / "review_queue.json",
            "top_opportunities": runtime_root / "top_opportunities_latest.json",
        },
    )

    assert metrics["summary"]["candidate_pool_latest"] == 0
    assert metrics["summary"]["ranked_candidate_count"] == 0
    assert metrics["candidate_pool_by_cycle"] == []
    assert metrics["rejection_reason_distribution"] == []
    assert metrics["score_distribution"] == []
    assert metrics["blockers_distribution"] == []
    assert metrics["allocation_summary"]["accepted_count"] == 0
    assert "missing:candidates_stream" in metrics["notes"]
    assert "no_surface_rows" in metrics["notes"]
