import json
import os
from collections import Counter
from pathlib import Path
import time

import core.orchestrator as orch_mod
from config import config as cfg


def _stub_orchestrator(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / "data"), raising=False)
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(Path(tmp_path / "logs" / "suggestions.jsonl")), raising=False)
    orch = orch_mod.Orchestrator.__new__(orch_mod.Orchestrator)
    monkeypatch.setattr(
        orch,
        "_feed_status_for_heartbeat",
        lambda: {
            "feed_ok": True,
            "ws_connected": True,
            "subscribed_option_tokens_count": 70,
            "missing_option_tokens_count": 0,
        },
    )
    return orch


def _write_suggestions_rows(tmp_path, rows):
    path = Path(cfg.LOGS_ROOT) / "suggestions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")
    return path


def _write_review_queue_rows(tmp_path, rows):
    path = Path(cfg.LOGS_ROOT) / "review_queue.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_suggestions_status_market_closed(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="cycle_complete",
        cycle_reason="cycle_complete",
        last_error="",
        market_mode="LIVE",
        market_open=False,
        symbols_scanned=0,
        candidates_seen=0,
        candidates_blocked=0,
        candidates_enqueued=0,
        blocker_counts=Counter(),
        suggestion_count=0,
    )

    payload = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert payload["status"] == "market_closed"
    assert payload["market_mode"] == "OFFHOURS"
    assert payload["market_open"] is False
    assert payload["suggestion_count"] == 0
    assert payload["reason"] == "MARKET_CLOSED"
    assert payload["subreason"] == ""
    assert payload["primary_blocker"] == "MARKET_CLOSED"
    assert engine["cycle_stage"] == "market_closed"
    assert engine["market_mode"] == "OFFHOURS"
    assert engine["market_open"] is False
    assert engine["primary_blocker"] == "MARKET_CLOSED"
    assert engine["reason"] == "MARKET_CLOSED"
    assert engine["subreason"] == ""


def test_suggestions_status_no_candidates(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="cycle_complete",
        cycle_reason="cycle_complete",
        last_error="",
        market_mode="LIVE",
        market_open=True,
        symbols_scanned=3,
        candidates_seen=0,
        candidates_blocked=0,
        candidates_enqueued=0,
        blocker_counts=Counter(),
        suggestion_count=0,
    )

    payload = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert payload["status"] == "no_candidates"
    assert payload["suggestion_count"] == 0
    assert payload["visible_suggestion_count"] == 0
    assert payload["current_cycle_suggestion_count"] == 0
    assert payload["reason"] == "no_candidates"
    assert payload["subreason"] == ""
    assert payload["primary_blocker"] == "NO_CANDIDATES"
    assert engine["cycle_stage"] == "no_candidates"
    assert engine["current_cycle_candidates_seen"] == 0
    assert engine["current_cycle_candidates_enqueued"] == 0
    assert engine["current_cycle_suggestion_count"] == 0
    assert engine["visible_suggestion_count"] == 0
    assert engine["primary_blocker"] == "NO_CANDIDATES"
    assert engine["reason"] == "no_candidates"


def test_engine_cycle_status_records_blocker_counts(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="scan_symbols",
        cycle_reason="blocked",
        last_error="",
        market_mode="LIVE",
        market_open=True,
        symbols_scanned=3,
        candidates_seen=1,
        candidates_blocked=3,
        candidates_enqueued=0,
        blocker_counts=Counter({"NO_LIVE_OPTION_FEED": 2, "PRICE_MISMATCH": 1}),
        suggestion_count=0,
    )

    payload = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    assert payload["candidates_blocked"] == 3
    assert payload["cycle_stage"] == "blocked"
    assert payload["primary_blocker"] == "NO_LIVE_OPTION_FEED"
    assert payload["reason"] == "candidates_blocked"
    assert payload["subreason"] == "NO_LIVE_OPTION_FEED"
    assert payload["top_blockers"][0] == {"reason": "NO_LIVE_OPTION_FEED", "count": 2}
    assert suggestions["status"] == "blocked"
    assert suggestions["primary_blocker"] == "NO_LIVE_OPTION_FEED"


def test_suggestions_status_ok_when_suggestions_generated(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="cycle_complete",
        cycle_reason="cycle_complete",
        last_error="",
        market_mode="LIVE",
        market_open=True,
        symbols_scanned=3,
        candidates_seen=2,
        candidates_blocked=0,
        candidates_enqueued=2,
        blocker_counts=Counter(),
        suggestion_count=2,
    )

    payload = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert payload["status"] == "ok"
    assert payload["suggestion_count"] == 0
    assert payload["visible_suggestion_count"] == 0
    assert payload["current_cycle_suggestion_count"] == 2
    assert payload["reason"] == "suggestions_generated"
    assert payload["subreason"] == ""
    assert engine["cycle_stage"] == "ok"
    assert engine["primary_blocker"] is None
    assert engine["reason"] == "suggestions_generated"
    assert engine["current_cycle_suggestion_count"] == 2


def test_status_files_stay_semantically_aligned_for_same_cycle(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="cycle_complete",
        cycle_reason="cycle_complete",
        last_error="",
        market_mode="SIM",
        market_open=False,
        symbols_scanned=0,
        candidates_seen=0,
        candidates_blocked=0,
        candidates_enqueued=0,
        blocker_counts=Counter(),
        suggestion_count=0,
    )

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "market_closed"
    assert engine["cycle_stage"] == "market_closed"
    assert suggestions["primary_blocker"] == "MARKET_CLOSED"
    assert engine["primary_blocker"] == "MARKET_CLOSED"
    assert suggestions["market_mode"] == "OFFHOURS"
    assert engine["market_mode"] == "OFFHOURS"


def test_visible_suggestions_override_no_candidates_runtime_status(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)
    _write_suggestions_rows(
        tmp_path,
        [
            {
                "trade_id": "T-VISIBLE-1",
                "advisory_visible": True,
                "execution_status": "advisory_only",
                "hard_blockers": [],
                "soft_penalties": ["STALE_OPTION_LTP"],
                "warnings": [],
                "blockers": ["STALE_OPTION_LTP"],
            }
        ],
    )

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="cycle_complete",
        cycle_reason="cycle_complete",
        last_error="",
        market_mode="LIVE",
        market_open=True,
        symbols_scanned=3,
        candidates_seen=0,
        candidates_blocked=0,
        candidates_enqueued=0,
        blocker_counts=Counter(),
        suggestion_count=0,
    )

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "ok"
    assert suggestions["suggestion_count"] == 1
    assert suggestions["visible_suggestion_count"] == 1
    assert suggestions["visible_advisory_count"] == 1
    assert suggestions["visible_queue_only_count"] == 0
    assert suggestions["visible_executable_count"] == 0
    assert suggestions["current_cycle_suggestion_count"] == 0
    assert suggestions["current_cycle_candidates_seen"] == 0
    assert suggestions["current_cycle_candidates_enqueued"] == 0
    assert suggestions["primary_blocker"] == "STALE_OPTION_LTP"
    assert suggestions["reason"] == "visible_suggestions_present"
    assert suggestions["subreason"] == ""
    assert engine["cycle_stage"] == "no_candidates"
    assert engine["candidates_seen"] == 0
    assert engine["candidates_enqueued"] == 0
    assert engine["current_cycle_candidates_seen"] == 0
    assert engine["current_cycle_candidates_enqueued"] == 0
    assert engine["current_cycle_suggestion_count"] == 0
    assert engine["visible_suggestion_count"] == 1


def test_visible_counts_follow_review_queue_snapshot_over_stale_suggestions_log(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)
    _write_suggestions_rows(
        tmp_path,
        [
            {
                "trade_id": "T-STALE-EXEC-1",
                "advisory_visible": True,
                "final_action": "EXECUTE",
                "execution_status": "advisory_only",
                "readiness": "READY",
                "hard_blockers": [],
                "soft_penalties": ["STALE_OPTION_LTP"],
                "warnings": [],
                "blockers": ["STALE_OPTION_LTP"],
            }
        ],
    )
    _write_review_queue_rows(
        tmp_path,
        [
            {
                "trade_id": "T-STALE-EXEC-1",
                "advisory_visible": True,
                "final_action": "ADVISORY_ONLY",
                "execution_status": "advisory_only",
                "execution_allowed": False,
                "quote_validation_status": "PRICE_MISMATCH",
                "hard_blockers": ["PRICE_MISMATCH"],
                "soft_penalties": ["PRICE_MISMATCH"],
                "warnings": [],
                "blockers": ["PRICE_MISMATCH"],
            }
        ],
    )

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="cycle_complete",
        cycle_reason="cycle_complete",
        last_error="",
        market_mode="LIVE",
        market_open=True,
        symbols_scanned=3,
        candidates_seen=0,
        candidates_blocked=0,
        candidates_enqueued=0,
        blocker_counts=Counter(),
        suggestion_count=0,
    )

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "ok"
    assert suggestions["suggestion_count"] == 1
    assert suggestions["visible_suggestion_count"] == 1
    assert suggestions["visible_executable_count"] == 0
    assert suggestions["visible_advisory_count"] == 1
    assert suggestions["primary_blocker"] == "PRICE_MISMATCH"
    assert suggestions["reason"] == "visible_suggestions_present"
    assert engine["visible_executable_count"] == 0


def test_stale_visible_sources_are_ignored_for_runtime_status(monkeypatch, tmp_path):
    orch = _stub_orchestrator(monkeypatch, tmp_path)
    monkeypatch.setattr(cfg, "STATUS_VISIBLE_SOURCE_MAX_AGE_SEC", 30.0, raising=False)
    suggestions_path = _write_suggestions_rows(
        tmp_path,
        [
            {
                "trade_id": "T-STALE-VISIBLE-1",
                "advisory_visible": True,
                "final_action": "QUEUE_ONLY",
                "execution_status": "queue_only",
                "hard_blockers": [],
                "soft_penalties": ["STALE_OPTION_LTP"],
                "warnings": [],
                "blockers": ["STALE_OPTION_LTP"],
            }
        ],
    )
    review_queue_path = _write_review_queue_rows(
        tmp_path,
        [
            {
                "trade_id": "T-STALE-VISIBLE-1",
                "advisory_visible": True,
                "final_action": "QUEUE_ONLY",
                "execution_status": "queue_only",
                "execution_allowed": False,
                "quote_validation_status": "STALE_OPTION_LTP",
                "hard_blockers": [],
                "soft_penalties": ["STALE_OPTION_LTP"],
                "warnings": [],
                "blockers": ["STALE_OPTION_LTP"],
            }
        ],
    )
    stale_epoch = time.time() - 600.0
    os.utime(suggestions_path, (stale_epoch, stale_epoch))
    os.utime(review_queue_path, (stale_epoch, stale_epoch))

    orch._write_cycle_status_files(
        cycle_ok=True,
        cycle_stage="cycle_complete",
        cycle_reason="cycle_complete",
        last_error="",
        market_mode="LIVE",
        market_open=True,
        symbols_scanned=3,
        candidates_seen=0,
        candidates_blocked=0,
        candidates_enqueued=0,
        blocker_counts=Counter(),
        suggestion_count=0,
    )

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "no_candidates"
    assert suggestions["visible_suggestion_count"] == 0
    assert suggestions["visible_executable_count"] == 0
    assert suggestions["primary_blocker"] == "NO_CANDIDATES"
    assert engine["visible_suggestion_count"] == 0
