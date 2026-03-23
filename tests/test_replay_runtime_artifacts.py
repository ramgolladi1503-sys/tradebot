from __future__ import annotations

import json

import core.replay_engine as replay_engine
from core.replay_engine import ReplayEngine


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _snapshot(payload, *, generated_at: str = "2026-03-19T14:05:00Z") -> dict:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "producer": "unit_test",
        "payload": payload,
    }


def _seed_runtime_artifacts(runtime_root):
    _write_json(
        runtime_root / "feed_runtime_latest.json",
        _snapshot({"ws_connected": True, "quote_age_sec": 0.4, "market_open": True}),
    )
    _write_json(
        runtime_root / "top_opportunities_latest.json",
        _snapshot(
            {
                "top_executable_opportunities": [
                    {
                        "trade_id": "T-EXEC-1",
                        "symbol": "NIFTY",
                        "timestamp": "2026-03-19T14:05:00Z",
                        "rank_global": 1,
                        "opportunity_score": 0.88,
                        "permission": "EXECUTE",
                        "readiness": "READY",
                        "allocation_reason": "allocated",
                        "allocation_score": 0.88,
                        "capital_assigned": 25000.0,
                        "size_multiplier_effective": 1.0,
                    }
                ],
                "top_advisory_opportunities": [
                    {
                        "trade_id": "T-ADV-1",
                        "symbol": "NIFTY",
                        "timestamp": "2026-03-19T14:05:30Z",
                        "rank_global": 2,
                        "opportunity_score": 0.82,
                        "permission": "ADVISORY_ONLY",
                        "readiness": "ADVISORY_ONLY",
                    }
                ],
                "top_executable_count": 1,
                "top_advisory_count": 1,
                "source_candidate_count": 2,
                "notes": [],
            }
        ),
    )
    _write_json(
        runtime_root / "advisory_latest.json",
        _snapshot(
            {
                "row_count": 1,
                "rows": [
                    {
                        "trade_id": "T-ADV-1",
                        "symbol": "NIFTY",
                        "timestamp": "2026-03-19T14:05:30Z",
                        "permission": "ADVISORY_ONLY",
                        "readiness": "ADVISORY_ONLY",
                        "execution_status": "advisory_only",
                        "display_entry": 121.5,
                    }
                ],
            }
        ),
    )
    _write_json(
        runtime_root / "observability" / "pipeline_funnel.json",
        {
            "schema_version": 1,
            "timestamp": "2026-03-19T14:06:00Z",
            "universe": 3,
            "candidates": 4,
            "scored": 3,
            "ready": 1,
            "executable": 1,
            "emitted": 1,
        },
    )
    _write_jsonl(
        runtime_root / "observability" / "trade_lifecycle.jsonl",
        [
            {
                "schema_version": 1,
                "timestamp": "2026-03-19T14:04:00Z",
                "trade_id": "T-CAND-1",
                "symbol": "NIFTY",
                "strategy": "CORE",
                "stage": "candidate_generation",
                "status": "created",
                "reason": "signal_breakout",
            },
            {
                "schema_version": 1,
                "timestamp": "2026-03-19T14:05:00Z",
                "trade_id": "T-EXEC-1",
                "symbol": "NIFTY",
                "strategy": "CORE",
                "stage": "scoring_ranking",
                "status": "selected",
                "reason": "top_ranked",
            },
            {
                "schema_version": 1,
                "timestamp": "2026-03-19T14:05:20Z",
                "trade_id": "T-EXEC-1",
                "symbol": "NIFTY",
                "strategy": "CORE",
                "stage": "readiness_gating",
                "status": "ready",
                "reason": "ready_for_execution",
            },
            {
                "schema_version": 1,
                "timestamp": "2026-03-19T14:05:40Z",
                "trade_id": "T-EXEC-1",
                "symbol": "NIFTY",
                "strategy": "CORE",
                "stage": "execution_feasibility",
                "status": "executable",
                "reason": "fresh_ask",
            },
            {
                "schema_version": 1,
                "timestamp": "2026-03-19T14:06:00Z",
                "trade_id": "T-EXEC-1",
                "symbol": "NIFTY",
                "strategy": "CORE",
                "stage": "emission_projection",
                "status": "emitted",
                "reason": "suggestions",
            },
        ],
    )
    _write_jsonl(
        runtime_root / "logs" / "suggestions.jsonl",
        [
            {
                "trade_id": "T-EXEC-1",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T14:06:00Z",
                "permission": "EXECUTE",
                "readiness": "READY",
                "execution_status": "executable",
            }
        ],
    )
    _write_json(
        runtime_root / "logs" / "review_queue.json",
        [
            {
                "trade_id": "T-ADV-1",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T14:05:30Z",
                "permission": "ADVISORY_ONLY",
                "readiness": "ADVISORY_ONLY",
                "execution_status": "advisory_only",
            }
        ],
    )
    _write_jsonl(
        runtime_root / "logs" / "rejected_candidates.jsonl",
        [
            {
                "trade_id": "T-BLOCK-1",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T14:04:30Z",
                "status": "blocked",
                "reason": "spread_too_wide",
            }
        ],
    )


def test_replay_runtime_artifacts_is_deterministic(tmp_path):
    runtime_root = tmp_path / "runtime"
    _seed_runtime_artifacts(runtime_root)

    first = ReplayEngine.replay_runtime_artifacts(
        symbol="NIFTY",
        start="2026-03-19T14:00:00Z",
        end="2026-03-19T14:10:00Z",
        runtime_root=runtime_root,
    )
    second = ReplayEngine.replay_runtime_artifacts(
        symbol="NIFTY",
        start="2026-03-19T14:00:00Z",
        end="2026-03-19T14:10:00Z",
        runtime_root=runtime_root,
    )

    assert first == second
    assert first["summary"]["candidate_count"] == 2
    assert first["summary"]["ranked_count"] == 2
    assert first["summary"]["advisory_count"] == 3
    assert first["summary"]["allocation_count"] == 1
    assert first["summary"]["execution_path_count"] == 3


def test_replay_runtime_artifacts_never_calls_live_paths(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    _seed_runtime_artifacts(runtime_root)

    def _should_not_call(*_args, **_kwargs):
        raise AssertionError("live_path_called")

    monkeypatch.setattr(replay_engine, "fetch_option_chain", _should_not_call)
    monkeypatch.setattr(replay_engine, "compute_indicators", _should_not_call)

    replay = ReplayEngine.replay_runtime_artifacts(
        symbol="NIFTY",
        start="2026-03-19T14:00:00Z",
        end="2026-03-19T14:10:00Z",
        runtime_root=runtime_root,
    )

    assert replay["summary"]["ranked_count"] == 2


def test_replay_runtime_artifacts_degrades_gracefully_when_optional_file_missing(tmp_path):
    runtime_root = tmp_path / "runtime"
    _seed_runtime_artifacts(runtime_root)
    (runtime_root / "top_opportunities_latest.json").unlink()

    replay = ReplayEngine.replay_runtime_artifacts(
        symbol="NIFTY",
        start="2026-03-19T14:00:00Z",
        end="2026-03-19T14:10:00Z",
        runtime_root=runtime_root,
    )

    assert "top_opportunities_latest" in replay["missing_artifacts"]
    assert replay["summary"]["ranked_count"] == 1
    assert replay["notes"].count("ranked_candidates_unavailable") == 0
