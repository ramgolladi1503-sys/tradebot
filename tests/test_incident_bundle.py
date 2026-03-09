from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.advisory_schema import serialize_advisory_row
from core.incident_bundle import build_incident_bundle_payload, generate_incident_bundle


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _advisory_row(
    *,
    symbol: str = "NIFTY",
    trade_id: str = "T-1",
    entry: float | None = 72.5,
    entry_status: str = "displayable",
    quote_age_sec: float | None = 1.2,
    blockers: list[str] | None = None,
    hard_blockers: list[str] | None = None,
    soft_penalties: list[str] | None = None,
    warnings: list[str] | None = None,
    execution_status: str = "advisory_only",
    readiness: str = "ADVISORY_ONLY",
    confidence_final: float = 0.74,
    instrument_token: int | None = 111,
    expiry: str = "2026-03-26",
    strike: float = 22500.0,
    right: str = "CE",
    timestamp_epoch: float = 1_700_000_000.0,
) -> dict:
    hard = list(hard_blockers or [])
    soft = list(soft_penalties or [])
    warn = list(warnings or [])
    all_blockers = list(blockers or [])
    if not all_blockers:
        all_blockers = []
        for source in (hard, soft, warn):
            for item in source:
                if item not in all_blockers:
                    all_blockers.append(item)
    payload = {
        "advisory_id": trade_id,
        "trade_id": trade_id,
        "symbol": symbol,
        "strategy_name": "CORE",
        "timestamp": _iso(timestamp_epoch),
        "instrument_type": "OPT",
        "execution_entry": entry,
        "execution_entry_source": "ask" if entry is not None else "none",
        "execution_entry_status": "executable" if entry is not None else "missing",
        "display_entry": entry,
        "display_entry_source": "ask" if entry is not None else "none",
        "display_entry_status": entry_status,
        "entry_reason": "live_quote" if entry is not None else None,
        "entry_clear_reason": None if entry is not None else "missing_executable_quote",
        "entry": entry,
        "entry_status": entry_status,
        "entry_source": "ask" if entry is not None else "none",
        "confidence": confidence_final,
        "confidence_raw": confidence_final,
        "confidence_penalty": 0.0,
        "confidence_final": confidence_final,
        "readiness": readiness,
        "blockers": all_blockers,
        "hard_blockers": hard,
        "soft_penalties": soft,
        "warnings": warn,
        "quote_source": "tick_store" if quote_age_sec is not None else "none",
        "quote_age_sec": quote_age_sec,
        "execution_status": execution_status,
        "advisory_visible": True,
        "is_executable": execution_status == "executable",
        "current_ltp": entry,
        "underlying_ltp": 22510.0,
        "instrument_token": instrument_token,
        "expiry_date": expiry,
        "strike": strike,
        "option_type": right,
        "freshness_reason": "quote_within_threshold" if quote_age_sec is not None else "quote_missing",
        "freshness_now_epoch": timestamp_epoch,
        "freshness_quote_epoch": timestamp_epoch - (quote_age_sec or 0.0) if quote_age_sec is not None else None,
        "freshness_candle_epoch": timestamp_epoch - 1.0,
        "freshness_threshold_sec": 8.0,
        "freshness_selected_source": "quote",
        "freshness_selected_age_sec": quote_age_sec,
    }
    return serialize_advisory_row(payload)


def _runtime_fixture(root: Path, *, symbol: str = "NIFTY", now_epoch: float = 1_700_000_100.0) -> dict[str, Path]:
    runtime_logs = root / ".runtime" / "logs"
    runtime_data = root / ".runtime"
    process_logs = root / "logs"
    runtime_logs.mkdir(parents=True, exist_ok=True)
    runtime_data.mkdir(parents=True, exist_ok=True)
    process_logs.mkdir(parents=True, exist_ok=True)

    _write_json(
        runtime_logs / "suggestions_status.json",
        {
            "status": "blocked",
            "market_mode": "LIVE",
            "market_open": True,
            "reason": "NO_LIVE_OPTION_FEED",
            "subreason": "",
            "primary_blocker": "NO_LIVE_OPTION_FEED",
        },
    )
    _write_json(
        runtime_logs / "engine_cycle_status.json",
        {
            "cycle_ok": True,
            "cycle_stage": "blocked",
            "market_mode": "LIVE",
            "market_open": True,
            "candidates_seen": 1,
            "candidates_blocked": 1,
            "candidates_enqueued": 0,
            "primary_blocker": "NO_LIVE_OPTION_FEED",
            "reason": "NO_LIVE_OPTION_FEED",
            "subreason": "",
        },
    )
    _write_json(
        runtime_logs / "feed_runtime_latest.json",
        {
            "feed_runtime_state": "RUNNING",
            "subscribed_tokens_count": 73,
            "subscribed_option_tokens_count": 70,
            "missing_option_tokens_count": 0,
            "last_tick_epoch_memory": now_epoch - 1.0,
            "last_option_tick_ts_by_symbol": {symbol: now_epoch - 1.2},
            "ws_connected": True,
        },
    )
    _write_json(
        runtime_logs / "freshness_latest.json",
        {
            "updated_at": _iso(now_epoch),
            "decisions": {
                symbol: {
                    "option_entry": {
                        "symbol": symbol,
                        "instrument_token": 111,
                        "decision_type": "option_entry",
                        "market_open": True,
                        "now_epoch": now_epoch,
                        "quote_epoch": now_epoch - 1.2,
                        "candle_epoch": now_epoch - 2.0,
                        "selected_epoch": now_epoch - 1.2,
                        "selected_source": "quote",
                        "quote_age_sec": 1.2,
                        "candle_age_sec": 2.0,
                        "selected_age_sec": 1.2,
                        "threshold_sec": 8.0,
                        "blocker": False,
                        "reason": "quote_within_threshold",
                        "trade_id": "T-1",
                        "ts_iso": _iso(now_epoch),
                    }
                }
            },
        },
    )
    _write_json(
        runtime_logs / "token_resolution.json",
        [
            {
                "symbol": symbol,
                "expiry": "2026-03-26",
                "count": 27,
                "option_count": 26,
                "option_fail_reason": None,
                "option_drop_reason": None,
                "tokens": [1, 111, 112],
            }
        ],
    )
    _write_json(
        runtime_data / "option_chain_latest.json",
        {
            symbol: [
                {
                    "symbol": symbol,
                    "expiry": "2026-03-26",
                    "strike": 22500.0,
                    "type": "CE",
                    "instrument_token": 111,
                    "tradingsymbol": f"{symbol}26MAR22500CE",
                    "quote_age_sec": 1.0,
                    "chain_source": "live",
                    "volume": 1200,
                    "oi": 5600,
                }
            ]
        },
    )
    return {
        "runtime_logs": runtime_logs,
        "runtime_data": runtime_data,
        "process_logs": process_logs,
    }


def test_incident_bundle_happy_path(tmp_path):
    paths = _runtime_fixture(tmp_path)
    suggestions_path = paths["runtime_logs"] / "suggestions.jsonl"
    _write_jsonl(
        suggestions_path,
        [
            _advisory_row(),
            _advisory_row(trade_id="T-OLD", blockers=["STALE_OPTION_LTP"], hard_blockers=["STALE_OPTION_LTP"], confidence_final=0.42),
        ],
    )
    now_epoch = 1_700_000_100.0
    (paths["process_logs"] / "main.log").write_text(
        f"{_iso(now_epoch - 60.0)} incident symbol=NIFTY entry_status=OK blocker=NONE\n",
        encoding="utf-8",
    )

    bundle_dir = generate_incident_bundle(
        symbol="NIFTY",
        trade_id="T-1",
        minutes=20,
        output_dir=tmp_path / "runtime" / "incidents",
        now_epoch=now_epoch,
        runtime_logs_dir=paths["runtime_logs"],
        runtime_data_dir=paths["runtime_data"],
        process_logs_dir=paths["process_logs"],
        suggestions_path=suggestions_path,
    )

    payload = json.loads((bundle_dir / "incident_bundle.json").read_text(encoding="utf-8"))
    text = (bundle_dir / "incident_bundle.txt").read_text(encoding="utf-8")

    for key in (
        "bundle_meta",
        "incident_summary",
        "feed_health",
        "advisory",
        "freshness",
        "blocker_state",
        "option_chain_health",
        "token_resolution",
        "log_snippets",
        "raw_sources",
    ):
        assert key in payload
    assert payload["advisory"]["entry"] == 72.5
    assert payload["blocker_state"]["current_blockers"] == []
    assert payload["freshness"]["freshness_reason"] == "quote_within_threshold"
    assert payload["token_resolution"]["option_token_present"] is True
    assert "entry=72.5" in text
    assert "Freshness:" in text
    assert "Token state:" in text


def test_incident_bundle_missing_advisory_file_still_valid(tmp_path):
    paths = _runtime_fixture(tmp_path)

    bundle, *_ = build_incident_bundle_payload(
        symbol="NIFTY",
        minutes=20,
        now_epoch=1_700_000_100.0,
        runtime_logs_dir=paths["runtime_logs"],
        runtime_data_dir=paths["runtime_data"],
        process_logs_dir=paths["process_logs"],
        suggestions_path=paths["runtime_logs"] / "missing_suggestions.jsonl",
    )

    assert bundle["advisory"]["missing"] is True
    assert bundle["incident_summary"]["status"] == "missing_advisory"


def test_incident_bundle_false_stale_preserves_raw_facts(tmp_path):
    paths = _runtime_fixture(tmp_path)
    suggestions_path = paths["runtime_logs"] / "suggestions.jsonl"
    _write_jsonl(
        suggestions_path,
        [
            _advisory_row(
                blockers=["STALE_OPTION_LTP"],
                hard_blockers=["STALE_OPTION_LTP"],
                quote_age_sec=2.0,
            )
        ],
    )

    bundle, *_ = build_incident_bundle_payload(
        symbol="NIFTY",
        trade_id="T-1",
        minutes=20,
        now_epoch=1_700_000_100.0,
        runtime_logs_dir=paths["runtime_logs"],
        runtime_data_dir=paths["runtime_data"],
        process_logs_dir=paths["process_logs"],
        suggestions_path=suggestions_path,
    )

    assert "STALE_OPTION_LTP" in bundle["blocker_state"]["current_blockers"]
    assert float(bundle["freshness"]["quote_age_sec"]) == 2.0
    assert float(bundle["freshness"]["stale_threshold_sec"]) == 8.0
    assert bundle["freshness"]["freshness_reason"] == "quote_within_threshold"


def test_incident_bundle_token_recovery_shows_latest_resolved_state(tmp_path):
    paths = _runtime_fixture(tmp_path)
    suggestions_path = paths["runtime_logs"] / "suggestions.jsonl"
    _write_jsonl(
        suggestions_path,
        [
            _advisory_row(trade_id="T-RECOVER", blockers=[], hard_blockers=[], instrument_token=111, entry=72.5),
            _advisory_row(
                trade_id="T-RECOVER",
                blockers=["NO_TOKEN"],
                hard_blockers=["NO_TOKEN"],
                instrument_token=None,
                entry=None,
                entry_status="missing",
                execution_status="blocked",
                readiness="BLOCKED",
            ),
        ],
    )

    bundle, *_ = build_incident_bundle_payload(
        symbol="NIFTY",
        trade_id="T-RECOVER",
        minutes=20,
        now_epoch=1_700_000_100.0,
        runtime_logs_dir=paths["runtime_logs"],
        runtime_data_dir=paths["runtime_data"],
        process_logs_dir=paths["process_logs"],
        suggestions_path=suggestions_path,
    )

    assert bundle["token_resolution"]["option_token_present"] is True
    assert bundle["blocker_state"]["current_blockers"] == []
    assert "NO_TOKEN" in bundle["blocker_state"]["previous_blockers"]
    assert bundle["advisory"]["entry"] == 72.5


def test_incident_bundle_log_filtering_keeps_recent_relevant_symbol_lines(tmp_path):
    paths = _runtime_fixture(tmp_path)
    suggestions_path = paths["runtime_logs"] / "suggestions.jsonl"
    _write_jsonl(suggestions_path, [_advisory_row()])
    now_epoch = 1_700_000_100.0
    (paths["process_logs"] / "main.log").write_text(
        "\n".join(
            [
                f"{_iso(now_epoch - 2000.0)} stale symbol=NIFTY entry_status=PRICE_MISMATCH",
                f"{_iso(now_epoch - 60.0)} live symbol=NIFTY entry_status=PRICE_MISMATCH quote_age_sec=12.0",
                f"{_iso(now_epoch - 40.0)} live symbol=BANKNIFTY entry_status=PRICE_MISMATCH quote_age_sec=12.0",
                f"{_iso(now_epoch - 30.0)} live symbol=NIFTY blocker=NO_TOKEN advisory=T-1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    bundle, *_ = build_incident_bundle_payload(
        symbol="NIFTY",
        trade_id="T-1",
        minutes=20,
        now_epoch=now_epoch,
        runtime_logs_dir=paths["runtime_logs"],
        runtime_data_dir=paths["runtime_data"],
        process_logs_dir=paths["process_logs"],
        suggestions_path=suggestions_path,
    )

    main_lines = bundle["log_snippets"]["files"]["main.log"]
    assert len(main_lines) == 2
    assert all("NIFTY" in line for line in main_lines)
    assert all("BANKNIFTY" not in line for line in main_lines)
