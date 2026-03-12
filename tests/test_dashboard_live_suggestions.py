from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import dashboard.streamlit_app_runtime as runtime
import pandas as pd
from core import advisory_schema
from dashboard.readers.advisory_reader import read_advisory_snapshot_rows


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_row(
    trade_id: str,
    *,
    entry: float,
    execution_entry: float | None = None,
    display_entry_source: str = "last",
    display_entry_status: str = "non_executable",
    execution_entry_source: str = "none",
    execution_entry_status: str = "non_executable",
    quote_source: str = "tick_store",
    readiness: str = "ADVISORY_ONLY",
    execution_status: str = "advisory_only",
    is_executable: bool = False,
    status: str = "ADVISORY_ONLY",
) -> dict:
    return advisory_schema.serialize_advisory_row(
        {
            "trade_id": trade_id,
            "advisory_id": trade_id,
            "timestamp": _iso_now(),
            "last_seen_ts": _iso_now(),
            "symbol": "NIFTY",
            "instrument": "OPT",
            "instrument_type": "OPT",
            "strategy_name": "CORE",
            "strategy_id": "CORE",
            "status": status,
            "permission": "EXECUTE" if is_executable else "ADVISORY_ONLY",
            "entry_status": display_entry_status,
            "readiness": readiness,
            "execution_status": execution_status,
            "advisory_visible": True,
            "is_executable": is_executable,
            "blockers": [],
            "quote_source": quote_source,
            "quote_age_sec": 0.5,
            "confidence": 0.7,
            "entry": entry,
            "entry_source": display_entry_source,
            "display_entry": entry,
            "display_entry_source": display_entry_source,
            "display_entry_status": display_entry_status,
            "execution_entry": execution_entry,
            "execution_entry_source": execution_entry_source,
            "execution_entry_status": execution_entry_status,
            "entry_reason": "display_from_last" if display_entry_source == "last" else "display_from_mark",
            "entry_clear_reason": None,
            "current_ltp": entry,
            "entry_price": entry,
            "expected_entry": entry,
            "warnings": [],
            "soft_penalties": [],
            "hard_blockers": [],
            "decision_explain": ["snapshot"],
            "market_open": True,
            "tradingsymbol": "NIFTYTESTCE",
            "instrument_token": 123456,
            "option_type": "CE",
            "type": "CE",
            "expiry_date": "2026-03-26",
            "strike": 23000,
            "side": "BUY",
        },
        allow_legacy=True,
    )


def test_load_live_suggestions_df_reads_latest_rows_only(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "suggestions.jsonl"
    rows = []
    for idx in range(5):
        rows.append(
            {
                "trade_id": f"T-{idx}",
                "advisory_id": f"T-{idx}",
                "timestamp": _iso_now(),
                "last_seen_ts": _iso_now(),
                "symbol": "NIFTY",
                "instrument": "OPT",
                "instrument_type": "OPT",
                "strategy_name": "CORE",
                "status": "READY",
                "permission": "EXECUTE",
                "entry_status": "OK",
                "readiness": "ADVISORY_ONLY" if idx == 4 else "READY",
                "blockers": ["STALE_OPTION_LTP"] if idx == 4 else [],
                "quote_source": "tick_store",
                "quote_age_sec": 0.5,
                "confidence": 0.7,
                "entry": 100.0 + idx,
                "current_ltp": 100.0 + idx,
                "entry_price": 100.0 + idx,
                "expected_entry": 100.0 + idx,
                "tradingsymbol": f"NIFTYTEST{idx}CE",
                "instrument_token": 1000 + idx,
                "option_type": "CE",
                "type": "CE",
                "expiry_date": "2026-03-26",
                "strike": 23000 + idx,
                "side": "BUY",
            }
        )
    suggestions_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=2)

    assert list(df_live["trade_id"]) == ["T-4", "T-3"]
    assert all(df_live["entry_status"].astype(str).str.lower() == "non_executable")
    assert float(df_live.iloc[0]["entry"]) == 104.0
    assert list(df_live.iloc[0]["blockers"]) == ["STALE_OPTION_LTP"]


def test_load_live_suggestions_df_prefers_advisory_latest_snapshot(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    advisory_snapshot_path = runtime_root / "advisory_latest.json"
    row = _snapshot_row(
        "T-SNAPSHOT-1",
        entry=123.45,
        execution_entry=123.45,
        display_entry_source="ask",
        display_entry_status="displayable",
        execution_entry_source="ask",
        execution_entry_status="executable",
        readiness="READY",
        execution_status="executable",
        is_executable=True,
        status="READY",
    )
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": {"rows": [row]}}),
        encoding="utf-8",
    )
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=5)

    assert list(df_live["trade_id"]) == ["T-SNAPSHOT-1"]
    assert float(df_live.iloc[0]["entry"]) == 123.45


def test_load_live_suggestions_df_downgrades_executable_row_without_entry(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    advisory_snapshot_path = runtime_root / "advisory_latest.json"
    row = _snapshot_row(
        "T-SNAPSHOT-MISSING-ENTRY",
        entry=None,
        execution_entry=None,
        display_entry_source="none",
        display_entry_status="missing",
        execution_entry_source="none",
        execution_entry_status="missing",
        readiness="READY",
        execution_status="executable",
        is_executable=True,
        status="READY",
    )
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": {"rows": [row]}}),
        encoding="utf-8",
    )
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=5)

    assert list(df_live["trade_id"]) == ["T-SNAPSHOT-MISSING-ENTRY"]
    loaded = df_live.iloc[0]
    assert pd.isna(loaded["entry"])
    assert str(loaded["entry_status"]) == "missing"
    assert str(loaded["execution_status"]) == "queue_only"
    assert str(loaded["readiness"]) == "QUEUE_ONLY"
    assert bool(loaded["is_executable"]) is False


def test_read_advisory_snapshot_rows_supports_top_level_rows(tmp_path):
    advisory_snapshot_path = tmp_path / "advisory_latest.json"
    row = _snapshot_row("T-TOP-LEVEL", entry=101.0)
    advisory_snapshot_path.write_text(json.dumps({"rows": [row]}), encoding="utf-8")

    out = read_advisory_snapshot_rows(advisory_snapshot_path, limit=5)

    assert out["state"] == "ok"
    assert out["errors"] == []
    assert [r["trade_id"] for r in out["rows"]] == ["T-TOP-LEVEL"]


def test_read_advisory_snapshot_rows_supports_payload_list(tmp_path):
    advisory_snapshot_path = tmp_path / "advisory_latest.json"
    row = _snapshot_row("T-PAYLOAD-LIST", entry=102.0)
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": [row]}),
        encoding="utf-8",
    )

    out = read_advisory_snapshot_rows(advisory_snapshot_path, limit=5)

    assert out["state"] == "ok"
    assert out["errors"] == []
    assert [r["trade_id"] for r in out["rows"]] == ["T-PAYLOAD-LIST"]


def test_read_advisory_snapshot_rows_marks_malformed_envelope_invalid(tmp_path):
    advisory_snapshot_path = tmp_path / "advisory_latest.json"
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": {"rows": {}}}),
        encoding="utf-8",
    )

    out = read_advisory_snapshot_rows(advisory_snapshot_path, limit=5)

    assert out["state"] == "invalid"
    assert out["rows"] == []
    assert "advisory_rows_not_list" in list(out["errors"])


def test_read_advisory_snapshot_rows_empty_snapshot_is_ok(tmp_path):
    advisory_snapshot_path = tmp_path / "advisory_latest.json"
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": {"rows": []}}),
        encoding="utf-8",
    )

    out = read_advisory_snapshot_rows(advisory_snapshot_path, limit=5)

    assert out["state"] == "ok"
    assert out["errors"] == []
    assert out["rows"] == []


def test_load_live_suggestions_df_returns_empty_on_invalid_advisory_snapshot(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    advisory_snapshot_path = runtime_root / "advisory_latest.json"
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": {"rows": {}}}),
        encoding="utf-8",
    )
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text(json.dumps({"trade_id": "T-RAW-1", "entry": 10.0}) + "\n", encoding="utf-8")

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=5)

    assert df_live.empty


def test_load_live_suggestions_status_reads_runtime_payload(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "blocked",
        "primary_blocker": "NO_LIVE_OPTION_FEED",
        "suggestion_count": 0,
    }
    (logs_root / "suggestions_status.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(runtime, "logs_dir", lambda: logs_root)

    loaded = runtime._load_live_suggestions_status()

    assert loaded["status"] == "blocked"
    assert loaded["primary_blocker"] == "NO_LIVE_OPTION_FEED"


def test_load_freshness_latest_reads_runtime_payload(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _iso_now(),
        "decisions": {
            "NIFTY": {
                "option_entry": {
                    "reason": "quote_within_threshold",
                    "blocker": False,
                    "now_epoch": 1700000000.0,
                    "quote_age_sec": 1.4,
                }
            }
        },
    }
    (logs_root / "freshness_latest.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(runtime, "logs_dir", lambda: logs_root)

    loaded = runtime._load_freshness_latest()

    assert loaded["decisions"]["NIFTY"]["option_entry"]["reason"] == "quote_within_threshold"


def test_load_freshness_latest_rejects_invalid_1970_style_payload(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": "1970-01-01T00:01:41+00:00",
        "decisions": {
            "NIFTY": {
                "option_entry": {
                    "reason": "quote_within_threshold",
                    "blocker": False,
                    "now_epoch": 101.0,
                    "quote_age_sec": 1.0,
                }
            }
        },
    }
    (logs_root / "freshness_latest.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(runtime, "logs_dir", lambda: logs_root)

    loaded = runtime._load_freshness_latest()

    assert loaded == {}


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.fragment = lambda *args, **kwargs: (lambda fn: fn)


def test_fetch_live_market_data_dashboard_suppresses_repeated_auth_failures(monkeypatch):
    fake_st = _FakeStreamlit()
    calls = {"count": 0}

    def _boom(*, allow_history_seed=True):
        calls["count"] += 1
        raise RuntimeError("TokenException: invalid access_token")

    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime, "fetch_live_market_data", _boom)
    monkeypatch.setattr(runtime, "_read_only_market_snapshot_rows", lambda: [])
    monkeypatch.setattr(runtime.time, "time", lambda: 100.0)

    assert runtime._fetch_live_market_data_dashboard("unit_test") == []
    assert runtime._fetch_live_market_data_dashboard("unit_test") == []
    assert calls["count"] == 0
    assert "dashboard_live_market_data_error_cooldown_until" not in fake_st.session_state


def test_should_enable_local_trade_refresh_allows_offhours_live_table(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["auto_refresh_enabled"] = True

    monkeypatch.setattr(runtime, "st", fake_st)

    assert runtime._should_enable_local_trade_refresh(show_active_view=False, show_advisory_view=True) is True
    assert runtime._should_enable_local_trade_refresh(show_active_view=False, show_advisory_view=False) is False


def test_fetch_day_type_events_dashboard_suppresses_repeated_auth_failures(monkeypatch):
    fake_st = _FakeStreamlit()
    calls = {"count": 0}

    def _boom(*, backfill=True, max_rows=0):
        calls["count"] += 1
        raise RuntimeError("[HIST_ERROR] TokenException incorrect api_key/access_token")

    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime, "load_day_type_events", _boom)
    monkeypatch.setattr(runtime.time, "time", lambda: 200.0)

    assert runtime._fetch_day_type_events_dashboard(caller="unit_test", max_rows=100) == []
    assert runtime._fetch_day_type_events_dashboard(caller="unit_test", max_rows=100) == []
    assert calls["count"] == 1
    assert float(fake_st.session_state["dashboard_history_cooldown_until_day_type_events"]) > 200.0


def test_get_daytype_history_uses_longer_cache_ttl(monkeypatch):
    fake_st = _FakeStreamlit()
    calls = {"count": 0}

    def _rows(*, caller: str, max_rows: int):
        calls["count"] += 1
        return [
            {"symbol": "NIFTY", "confidence": 0.7},
            {"symbol": "NIFTY", "confidence": 0.8},
        ]

    now = {"ts": 100.0}
    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime, "_fetch_day_type_events_dashboard", _rows)
    monkeypatch.setattr(runtime.time, "time", lambda: now["ts"])

    first = runtime._get_daytype_history("NIFTY")
    now["ts"] = 140.0
    second = runtime._get_daytype_history("NIFTY")

    assert first == [0.7, 0.8]
    assert second == [0.7, 0.8]
    assert calls["count"] == 1


def test_fetch_live_market_data_dashboard_disables_history_seed(monkeypatch):
    fake_st = _FakeStreamlit()
    calls = []

    def _fetch_live_market_data(*, allow_history_seed=True):
        calls.append(bool(allow_history_seed))
        return []

    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime, "fetch_live_market_data", _fetch_live_market_data)
    monkeypatch.setattr(
        runtime,
        "_read_only_market_snapshot_rows",
        lambda: [{"symbol": "NIFTY", "instrument": "OPT", "option_chain": []}],
    )

    assert runtime._fetch_live_market_data_dashboard("unit_test_dashboard") == [
        {"symbol": "NIFTY", "instrument": "OPT", "option_chain": []}
    ]
    assert calls == []


def test_refresh_trade_state_skips_state_engine_in_read_only_mode(monkeypatch):
    fake_st = _FakeStreamlit()
    calls = {"count": 0}

    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime.cfg, "UI_DASHBOARD_READ_ONLY", True, raising=False)
    monkeypatch.setattr(runtime, "run_state_engine_if_due", lambda **kwargs: calls.__setitem__("count", calls["count"] + 1))

    assert runtime._refresh_trade_state() is False
    assert calls["count"] == 0


def test_fetch_day_type_events_dashboard_reads_without_backfill(monkeypatch):
    fake_st = _FakeStreamlit()
    calls = []

    def _loader(*, backfill=False, max_rows=0):
        calls.append({"backfill": backfill, "max_rows": max_rows})
        return []

    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime, "load_day_type_events", _loader)
    monkeypatch.setattr(runtime.time, "time", lambda: 200.0)

    assert runtime._fetch_day_type_events_dashboard(caller="unit_test", max_rows=100) == []
    assert calls == [{"backfill": False, "max_rows": 100}]


def test_load_live_suggestions_df_logs_invalid_schema_rows(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "suggestions.jsonl"
    logs_root = tmp_path / "logs"
    rows = [
        {
            "trade_id": "T-BAD",
            "timestamp": _iso_now(),
            "symbol": "NIFTY",
            "entry_status": "OK",
        },
        {
            "trade_id": "T-GOOD",
            "advisory_id": "T-GOOD",
            "timestamp": _iso_now(),
            "last_seen_ts": _iso_now(),
            "symbol": "NIFTY",
            "instrument_type": "OPT",
            "strategy_name": "CORE",
            "entry": 72.5,
            "entry_status": "VALID",
            "confidence": 0.8,
            "readiness": "ADVISORY_ONLY",
            "blockers": ["STALE_OPTION_LTP"],
            "quote_source": "tick_store",
            "quote_age_sec": 0.4,
        },
    ]
    suggestions_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))
    monkeypatch.setattr(advisory_schema, "logs_dir", lambda: logs_root)

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert list(df_live["advisory_id"]) == ["T-GOOD"]
    payload = json.loads((logs_root / "advisory_schema_errors.jsonl").read_text().strip())
    assert payload["source"] == "dashboard.live_suggestions"
    assert payload["trade_id"] == "T-BAD"


def test_load_live_suggestions_df_preserves_canonical_advisory_fields(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "suggestions.jsonl"
    row = {
        "trade_id": "T-CANONICAL",
        "strategy_id": "CORE",
        "advisory_id": "ADV-1",
        "timestamp": _iso_now(),
        "last_seen_ts": _iso_now(),
        "symbol": "NIFTY",
        "instrument_type": "OPT",
        "strategy_name": "CORE",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "non_executable",
        "display_entry": 72.5,
        "display_entry_source": "mark",
        "display_entry_status": "non_executable",
        "entry_reason": "display_from_mark",
        "entry_clear_reason": None,
        "entry": 72.5,
        "entry_status": "non_executable",
        "confidence": 0.71,
        "confidence_base": 0.82,
        "confidence_raw": 0.82,
        "confidence_penalty": 0.11,
        "confidence_penalty_total": 0.11,
        "confidence_penalty_reasons": ["STALE_OPTION_LTP"],
        "confidence_final": 0.71,
        "readiness": "ADVISORY_ONLY",
        "hard_blockers": [],
        "soft_penalties": ["STALE_OPTION_LTP"],
        "warnings": ["NO_LIVE_OPTION_FEED"],
        "blockers": ["STALE_OPTION_LTP", "NO_LIVE_OPTION_FEED"],
        "quote_source": "tick_store",
        "quote_age_sec": 4.2,
        "advisory_visible": True,
        "is_executable": False,
        "execution_status": "advisory_only",
        "entry_source": "mark",
        "current_ltp": 72.5,
        "decision_explain": [{"code": "TRACE", "message": "kept"}],
        "market_open": True,
    }
    suggestions_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert len(df_live) == 1
    loaded = df_live.iloc[0]
    assert float(loaded["entry"]) == 72.5
    assert float(loaded["confidence_base"]) == 0.82
    assert float(loaded["confidence_final"]) == 0.71
    assert float(loaded["confidence_penalty_total"]) == 0.11
    assert list(loaded["confidence_penalty_reasons"]) == ["STALE_OPTION_LTP"]
    assert list(loaded["hard_blockers"]) == []
    assert list(loaded["soft_penalties"]) == ["STALE_OPTION_LTP"]
    assert list(loaded["warnings"]) == ["NO_LIVE_OPTION_FEED"]
    assert str(loaded["execution_status"]) == "advisory_only"
    assert str(loaded["entry_source"]) == "mark"
    assert str(loaded["display_entry_status"]) == "non_executable"
    assert loaded["decision_explain"] == [{"code": "TRACE", "message": "kept"}]
    assert bool(loaded["market_open"]) is True


def test_load_live_suggestions_df_keeps_queue_only_row_honest_when_entry_missing(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "suggestions.jsonl"
    row = {
        "trade_id": "T-QUEUE-MISSING",
        "strategy_id": "CORE",
        "advisory_id": "ADV-QUEUE-MISSING",
        "timestamp": _iso_now(),
        "last_seen_ts": _iso_now(),
        "symbol": "NIFTY",
        "instrument_type": "OPT",
        "strategy_name": "CORE",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "missing",
        "display_entry": None,
        "display_entry_source": "none",
        "display_entry_status": "missing",
        "entry_reason": None,
        "entry_clear_reason": "missing_entry",
        "entry": None,
        "entry_status": "missing",
        "confidence": 0.41,
        "confidence_raw": 0.41,
        "confidence_penalty": 0.0,
        "confidence_final": 0.41,
        "readiness": "QUEUE_ONLY",
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
        "blockers": [],
        "quote_source": "tick_store",
        "quote_age_sec": 2.0,
        "advisory_visible": True,
        "is_executable": False,
        "execution_status": "queue_only",
        "entry_source": "none",
        "decision_explain": [],
        "market_open": True,
    }
    suggestions_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert len(df_live) == 1
    loaded = df_live.iloc[0]
    assert pd.isna(loaded["entry"])
    assert str(loaded["entry_status"]) == "missing"
    assert str(loaded["execution_status"]) == "queue_only"
    assert str(loaded["readiness"]) == "QUEUE_ONLY"
    assert bool(loaded["is_executable"]) is False


def test_dashboard_view_matches_engine_row_after_recovery(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "suggestions.jsonl"
    stale_row = {
        "trade_id": "T-RECOVER",
        "strategy_id": "CORE",
        "advisory_id": "ADV-RECOVER",
        "timestamp": "2026-03-08T14:30:00+00:00",
        "last_seen_ts": "2026-03-08T14:30:00+00:00",
        "symbol": "NIFTY",
        "instrument_type": "OPT",
        "strategy_name": "CORE",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "missing",
        "display_entry": 72.5,
        "display_entry_source": "mark",
        "display_entry_status": "displayable",
        "entry_reason": "display_from_mark",
        "entry_clear_reason": "stale_quote",
        "entry": 72.5,
        "entry_status": "displayable",
        "confidence": 0.55,
        "confidence_raw": 0.55,
        "confidence_penalty": 0.0,
        "confidence_final": 0.55,
        "readiness": "BLOCKED",
        "hard_blockers": ["STALE_OPTION_LTP"],
        "soft_penalties": [],
        "warnings": [],
        "blockers": ["STALE_OPTION_LTP"],
        "quote_source": "tick_store",
        "quote_age_sec": 12.0,
        "advisory_visible": True,
        "is_executable": False,
        "execution_status": "blocked",
        "entry_source": "mark",
        "freshness_reason": "quote_exceeds_threshold",
        "freshness_market_open": True,
        "decision_explain": [],
        "market_open": True,
    }
    fresh_row = {
        "trade_id": "T-RECOVER",
        "strategy_id": "CORE",
        "advisory_id": "ADV-RECOVER",
        "timestamp": "2026-03-08T14:31:00+00:00",
        "last_seen_ts": "2026-03-08T14:31:00+00:00",
        "symbol": "NIFTY",
        "instrument_type": "OPT",
        "strategy_name": "CORE",
        "execution_entry": 73.0,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "display_entry": 73.0,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "entry_reason": "execution_from_ask",
        "entry_clear_reason": None,
        "entry": 73.0,
        "entry_status": "displayable",
        "confidence": 0.62,
        "confidence_raw": 0.62,
        "confidence_penalty": 0.0,
        "confidence_final": 0.62,
        "readiness": "ADVISORY_ONLY",
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
        "blockers": [],
        "quote_source": "tick_store",
        "quote_age_sec": 1.2,
        "advisory_visible": True,
        "is_executable": False,
        "execution_status": "advisory_only",
        "entry_source": "ask",
        "freshness_reason": "quote_within_threshold",
        "freshness_market_open": True,
        "decision_explain": [],
        "market_open": True,
    }
    suggestions_path.write_text(
        json.dumps(stale_row) + "\n" + json.dumps(fresh_row) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert len(df_live) == 1
    loaded = df_live.iloc[0]
    assert loaded["trade_id"] == "T-RECOVER"
    assert float(loaded["entry"]) == 73.0
    assert loaded["readiness"] == "ADVISORY_ONLY"
    assert list(loaded["hard_blockers"]) == []
    assert list(loaded["blockers"]) == []
    assert float(loaded["quote_age_sec"]) == 1.2
    assert loaded["freshness_reason"] == "quote_within_threshold"


def test_select_visible_advisory_rows_keeps_visible_non_executable_rows():
    df = pd.DataFrame(
        [
            {
                "trade_id": "T-ADV",
                "advisory_visible": True,
                "execution_status": "advisory_only",
                "entry": 72.5,
                "entry_status": "non_executable",
                "hard_blockers": [],
                "soft_penalties": ["STALE_OPTION_LTP"],
                "warnings": [],
                "last_seen_ts": _iso_now(),
            },
            {
                "trade_id": "T-BLOCK",
                "advisory_visible": True,
                "execution_status": "blocked",
                "entry": 70.0,
                "entry_status": "displayable",
                "hard_blockers": ["NO_LIVE_OPTION_FEED"],
                "soft_penalties": [],
                "warnings": [],
                "last_seen_ts": _iso_now(),
            },
            {
                "trade_id": "T-HIDDEN",
                "advisory_visible": False,
                "execution_status": "advisory_only",
                "entry": 69.0,
                "entry_status": "displayable",
                "hard_blockers": [],
                "soft_penalties": [],
                "warnings": [],
                "last_seen_ts": _iso_now(),
            },
        ]
    )

    out = runtime._select_visible_advisory_rows(df)

    assert set(out["trade_id"]) == {"T-ADV", "T-BLOCK"}


def test_chart_view_does_not_fetch_history_until_requested(monkeypatch):
    class _ChartFakeStreamlit:
        def __init__(self):
            self.infos = []

        def checkbox(self, label, value=False, key=None):
            if label == "Chart view":
                return True
            if label == "Load chart history":
                return False
            if label == "Show option line":
                return False
            return value

        def selectbox(self, label, options=None, index=0, key=None):
            options = list(options or [])
            return options[index] if options else None

        def info(self, message):
            self.infos.append(str(message))

        def warning(self, message):
            self.infos.append(str(message))

        def plotly_chart(self, *args, **kwargs):
            raise AssertionError("plot should not render when chart history is disabled")

    fake_st = _ChartFakeStreamlit()
    trade_df = pd.DataFrame(
        [
            {
                "trade_id": "T-CHART-1",
                "symbol": "NIFTY",
                "timestamp_epoch_ms": 1_700_000_000_000,
                "last_seen_ts": _iso_now(),
            }
        ]
    )

    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime, "section_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime, "_prepare_trade_display_df", lambda df: df.copy())
    monkeypatch.setattr(runtime, "_apply_executable_pricing", lambda df: df.copy())
    monkeypatch.setattr(runtime, "_safe_sort_by_last_seen", lambda df: df.copy())
    monkeypatch.setattr(runtime, "_stable_trade_key", lambda row: str(row.get("trade_id") or "T-CHART-1"))
    monkeypatch.setattr(runtime, "_infer_underlying_symbol", lambda trade: "NIFTY")
    monkeypatch.setattr(runtime, "get_underlying_candles", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("history should not load")))
    monkeypatch.setattr(runtime, "get_option_candles_or_snapshots", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("option history should not load")))

    runtime._render_chart_view_panel(trade_df)

    assert any("Chart history is disabled until requested" in msg for msg in fake_st.infos)
