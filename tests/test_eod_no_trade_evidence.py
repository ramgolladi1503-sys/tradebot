from __future__ import annotations

import csv
import json
from pathlib import Path

from core.eod_no_trade_evidence import (
    analyze_replay_file,
    analyze_tick_file,
    build_eod_no_trade_evidence,
    eod_no_trade_evidence_to_markdown,
    write_eod_no_trade_evidence,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_tick_integrity_reports_missing_sensex_and_monotonic_counts(tmp_path: Path) -> None:
    ticks = tmp_path / "ticks.jsonl"
    _write_jsonl(
        ticks,
        [
            {"ts": 1.0, "symbol": "NIFTY 50", "ltp": 24000},
            {"ts": 2.0, "symbol": "NIFTY26JUN24000CE", "ltp": 100.0, "bid": 99.0, "ask": 101.0},
            {"ts": 3.0, "symbol": "NIFTY BANK", "ltp": 58100},
        ],
    )

    report = analyze_tick_file(ticks)

    assert report["records"] == 3
    assert report["non_monotonic_ticks"] == 0
    assert report["structurally_usable"] is True
    assert report["present_index_symbols"] == ("NIFTY 50", "NIFTY BANK")
    assert report["missing_index_symbols"] == ("SENSEX", "INDIA VIX")


def test_replay_coverage_is_diagnostic_not_production_equivalent(tmp_path: Path) -> None:
    replay = tmp_path / "active_options_replay.json"
    replay.write_text(
        json.dumps(
            [
                {"timestamp": "2026-06-25T09:15:00", "NIFTY_INDEX": 24000, "BANKNIFTY_INDEX": 58000},
                {"timestamp": "2026-06-25T09:15:01", "NIFTY_INDEX": 24001, "BANKNIFTY_INDEX": 58001},
            ]
        ),
        encoding="utf-8",
    )

    report = analyze_replay_file(replay)

    assert report["snapshot_count"] == 2
    assert report["present_keys"] == ("NIFTY_INDEX", "BANKNIFTY_INDEX")
    assert "SENSEX" in report["missing_keys"]
    assert report["diagnostic_only"] is True
    assert report["production_equivalent"] is False


def test_eod_evidence_preserves_safety_flags_and_runtime_blockers(tmp_path: Path) -> None:
    ticks = tmp_path / "ticks.jsonl"
    replay = tmp_path / "active_options_replay.json"
    runtime = tmp_path / ".runtime"
    wfa = tmp_path / "oos_trades.csv"
    _write_jsonl(
        ticks,
        [
            {"ts": 1.0, "symbol": "NIFTY 50", "ltp": 24000},
            {"ts": 2.0, "symbol": "NIFTY BANK", "ltp": 58100},
        ],
    )
    replay.write_text(
        json.dumps([{"timestamp": "2026-06-25T09:15:00", "NIFTY_INDEX": 24000, "BANKNIFTY_INDEX": 58100}]),
        encoding="utf-8",
    )
    _write_json(
        runtime / "strategy_no_qualified_reasons_latest.json",
        {"read_only": True, "is_order_action": False, "broker_api_called": False, "not_applicable_reason": "feed_blocked", "raw_candidate_count": 0},
    )
    _write_json(
        runtime / "candidate_starvation_trace_latest.json",
        {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "latest_global_blocker": "FEED_LTP_STALE",
            "first_zero_stage": "no_raw_candidates",
            "raw_candidate_count": 0,
            "last_candidate_funnel_by_symbol": {"NIFTY": {"raw_candidate_count": 2}},
        },
    )
    _write_json(runtime / "phase2_rejection_latest.json", {"phase2_input_count": 0, "phase2_starvation_reason": "upstream_starvation"})
    _write_json(runtime / "notrade_reason_truth_latest.json", {"primary_reason": "unknown", "phase2_input_candidate_count": 0})
    _write_csv(
        wfa,
        [
            {"pl": "10.0", "strategy": "ORB", "test_year": "2022", "outcome": "TARGET", "is_oos": "False"},
            {"pl": "-20.0", "strategy": "MeanReversion", "test_year": "2022", "outcome": "STOP", "is_oos": "False"},
        ],
    )

    evidence = build_eod_no_trade_evidence(
        trade_date="2026-06-25",
        tick_path=ticks,
        replay_path=replay,
        runtime_dir=runtime,
        wfa_csv_path=wfa,
    )
    payload = evidence.to_payload()

    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["runtime_artifacts"]["top_level_blockers"]["latest_global_blocker"] == "FEED_LTP_STALE"
    assert payload["runtime_artifacts"]["phase2_input_candidate_count"] == 0
    assert payload["wfa_proxy"]["proxy_only"] is True
    assert payload["wfa_proxy"]["edge_claimed"] is False
    assert "wfa_is_oos_flags_are_not_all_true" in payload["warnings"]


def test_writer_emits_json_and_markdown_without_claiming_edge(tmp_path: Path) -> None:
    ticks = tmp_path / "ticks.jsonl"
    replay = tmp_path / "active_options_replay.json"
    _write_jsonl(ticks, [{"ts": 1.0, "symbol": "NIFTY 50", "ltp": 24000}])
    replay.write_text(json.dumps([{"timestamp": "2026-06-25T09:15:00", "NIFTY_INDEX": 24000}]), encoding="utf-8")
    evidence = build_eod_no_trade_evidence(
        trade_date="2026-06-25",
        tick_path=ticks,
        replay_path=replay,
        runtime_dir=tmp_path / ".runtime",
        wfa_csv_path=None,
    )

    json_path, markdown_path = write_eod_no_trade_evidence(
        evidence,
        json_path=tmp_path / "evidence.json",
        markdown_path=tmp_path / "evidence.md",
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["broker_api_called"] is False
    assert payload["append"] is False
    assert "No broker APIs called" in markdown
    assert "Production equivalent: `False`" in markdown
    assert "Edge claimed" in markdown
    assert "Do not loosen freshness" in markdown
    assert eod_no_trade_evidence_to_markdown(evidence) == markdown
