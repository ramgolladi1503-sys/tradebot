from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import dashboard.streamlit_app_runtime as runtime
import pandas as pd
from core import advisory_schema
from core.advisory_row_integrity import CANONICAL_ROW_KIND
from dashboard.readers.advisory_reader import read_advisory_snapshot_rows
from dashboard.ui.table_model import CANONICAL_COLUMNS, select_display_df


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_row(
    trade_id: str,
    *,
    entry: float,
    execution_entry: float | None = None,
    display_entry_source: str = "last",
    display_entry_status: str = "displayable",
    execution_entry_source: str = "none",
    execution_entry_status: str = "non_executable",
    quote_source: str = "tick_store",
    readiness: str = "ADVISORY_ONLY",
    execution_status: str = "advisory_only",
    is_executable: bool = False,
    status: str = "ADVISORY_ONLY",
) -> dict:
    stop_loss = None
    target = None
    if entry is not None:
        stop_loss = round(float(entry) - 10.0, 2)
        target = round(float(entry) + 10.0, 2)
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
            "row_kind": CANONICAL_ROW_KIND if entry is not None else "advisory_only",
            "stop": stop_loss,
            "stop_loss": stop_loss,
            "target": target,
            "non_canonical_levels": entry is None,
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


def _write_advisory_snapshot(tmp_path, rows):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    advisory_snapshot_path = runtime_root / "advisory_latest.json"
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": {"rows": rows}}),
        encoding="utf-8",
    )
    return advisory_snapshot_path


def _write_top_opportunities_snapshot(
    tmp_path,
    top_executable,
    top_advisory,
    *,
    generated_at: str | None = None,
):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    path = runtime_root / "top_opportunities_latest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": generated_at or _iso_now(),
                "producer": "test",
                "payload": {
                    "top_executable_opportunities": list(top_executable),
                    "top_advisory_opportunities": list(top_advisory),
                    "top_executable_count": len(top_executable),
                    "top_advisory_count": len(top_advisory),
                    "source_candidate_count": len(top_executable) + len(top_advisory),
                    "notes": [],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_live_suggestions_df_returns_empty_when_snapshot_missing_even_if_tail_exists(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text(json.dumps({"trade_id": "T-TAIL"}) + "\n", encoding="utf-8")
    advisory_snapshot_path = tmp_path / "runtime" / "advisory_latest.json"

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=2)

    assert df_live.empty


def test_reject_reason_summary_populates():
    df = pd.DataFrame(
        [
            {"trade_id": "T-1", "primary_blocker": "stale_quote"},
            {"trade_id": "T-2", "primary_blocker": "stale_quote"},
            {"trade_id": "T-3", "primary_blocker": "missing_liquidity"},
            {"trade_id": "T-4", "primary_blocker": ""},
        ]
    )

    summary = runtime._build_reject_reason_summary(df)

    assert list(summary["primary_blocker"]) == ["stale_quote", "missing_liquidity", "UNSPECIFIED"]
    assert list(summary["count"]) == [2, 1, 1]


def test_load_live_suggestions_df_prefers_advisory_latest_snapshot(tmp_path, monkeypatch):
    advisory_snapshot_path = tmp_path / "runtime" / "advisory_latest.json"
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
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, [row])
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=5)

    assert list(df_live["trade_id"]) == ["T-SNAPSHOT-1"]
    assert float(df_live.iloc[0]["entry"]) == 123.45


def test_load_live_suggestions_df_identity_includes_option_side(tmp_path, monkeypatch):
    advisory_snapshot_path = tmp_path / "runtime" / "advisory_latest.json"
    row = _snapshot_row(
        "T-SNAPSHOT-PE",
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
    row["option_type"] = None
    row["type"] = None
    row["right"] = None
    row["tradingsymbol"] = "NIFTY26MAR1723850PE"
    row["expiry_date"] = "2026-03-17"
    row["strike"] = 23850
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, [row])
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=5)
    display = select_display_df(df_live, "advisory")

    assert len(display) == 1
    assert display.iloc[0]["identity"] == "NIFTY\n2026-03-17\n23850 PE"


def test_load_live_suggestions_df_filters_out_non_canonical_row_without_entry(tmp_path, monkeypatch):
    advisory_snapshot_path = tmp_path / "runtime" / "advisory_latest.json"
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
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, [row])
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=5)

    assert df_live.empty


def test_load_live_suggestions_df_filters_display_only_executable_row_from_canonical_table(tmp_path, monkeypatch):
    advisory_snapshot_path = tmp_path / "runtime" / "advisory_latest.json"
    row = _snapshot_row(
        "T-SNAPSHOT-DISPLAY-ONLY",
        entry=72.5,
        execution_entry=None,
        display_entry_source="mark",
        display_entry_status="displayable",
        execution_entry_source="none",
        execution_entry_status="missing",
        readiness="READY",
        execution_status="executable",
        is_executable=True,
        status="READY",
    )
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, [row])
    suggestions_path = tmp_path / "suggestions.jsonl"
    suggestions_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(suggestions_path))

    df_live = runtime._load_live_suggestions_df(limit=5)

    assert df_live.empty


def test_load_top_opportunities_frames_preserves_executable_and_advisory_lists(tmp_path, monkeypatch):
    top_exec_path = _write_top_opportunities_snapshot(
        tmp_path,
        top_executable=[
            _snapshot_row(
                "T-TOP-EXEC",
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
        ],
        top_advisory=[
            _snapshot_row(
                "T-TOP-ADV",
                entry=72.5,
                execution_entry=None,
                display_entry_source="mark",
                display_entry_status="displayable",
                execution_entry_source="none",
                execution_entry_status="non_executable",
                readiness="ADVISORY_ONLY",
                execution_status="advisory_only",
                is_executable=False,
                status="ADVISORY_ONLY",
            )
        ],
    )

    monkeypatch.setattr(runtime, "TOP_OPPORTUNITIES_LATEST_PATH", top_exec_path)

    frames = runtime._load_top_opportunities_frames(limit=5)

    assert list(frames["top_executable"]["trade_id"]) == ["T-TOP-EXEC"]
    assert list(frames["top_advisory"]["trade_id"]) == ["T-TOP-ADV"]
    assert str(frames["top_executable"].iloc[0]["execution_status"]) == "executable"
    assert str(frames["top_advisory"].iloc[0]["execution_status"]) == "advisory_only"
    assert float(frames["top_executable"].iloc[0]["entry"]) == 123.45
    assert float(frames["top_advisory"].iloc[0]["entry"]) == 72.5


def test_load_top_opportunities_frames_filters_stale_rows_inside_fresh_snapshot(tmp_path, monkeypatch):
    stale_row = _snapshot_row(
        "T-TOP-STALE",
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
    stale_row["display_ts_epoch"] = 1_775_718_795.304797
    stale_row["display_ts_ist"] = "2026-04-09 12:43:15 IST"
    top_exec_path = _write_top_opportunities_snapshot(
        tmp_path,
        top_executable=[stale_row],
        top_advisory=[],
        generated_at="2026-04-22T06:38:05.130520Z",
    )

    monkeypatch.setattr(runtime, "TOP_OPPORTUNITIES_LATEST_PATH", top_exec_path)
    monkeypatch.setattr(runtime, "now_local", lambda: datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(runtime.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True, raising=False)

    frames = runtime._load_top_opportunities_frames(limit=5)

    assert frames["top_executable"].empty
    assert frames["top_advisory"].empty


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
        self.sidebar = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def markdown(self, *args, **kwargs):
        return None

    def columns(self, count):
        return [self for _ in range(int(count))]

    def metric(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def multiselect(self, label, options=None, default=None, key=None):
        if default is not None:
            return list(default)
        return list(options or [])

    def text_input(self, label, value="", key=None):
        return value

    def slider(self, *args, **kwargs):
        return kwargs.get("value")

    def selectbox(self, label, options, index=0, key=None):
        if not options:
            return None
        return options[index if 0 <= index < len(options) else 0]

    def checkbox(self, label, value=False, key=None):
        return value


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


def test_render_trade_explorer_sidebar_filters_handles_raw_rows_without_trade_date(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(runtime, "st", fake_st)
    raw_df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "tradingsymbol": "NIFTY26APR24000CE",
                "timestamp": _iso_now(),
                "run_id": "RUN-1",
                "option_type": "CE",
                "confidence": 0.55,
            }
        ]
    )

    filters = runtime._render_trade_explorer_sidebar_filters(raw_df)

    assert isinstance(filters, dict)
    assert filters["selected_cols"]
    assert filters["show_charts"] is True


def test_render_trade_explorer_panel_handles_raw_rows_without_trade_date(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(runtime, "st", fake_st)
    raw_df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "tradingsymbol": "NIFTY26APR24000CE",
                "timestamp": _iso_now(),
                "run_id": "RUN-1",
                "option_type": "CE",
                "confidence": 0.55,
                "permission": "EXECUTE",
                "final_action": "EXECUTE",
            }
        ]
    )

    runtime._render_trade_explorer_panel(raw_df, {"show_charts": False})


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
    advisory_snapshot_path = tmp_path / "runtime" / "advisory_latest.json"
    logs_root = tmp_path / "logs"
    rows = [
        {
            "trade_id": "T-BAD",
            "timestamp": _iso_now(),
            "symbol": "NIFTY",
            "entry_status": "OK",
        },
        _snapshot_row(
            "T-GOOD",
            entry=72.5,
            execution_entry=72.5,
            execution_entry_source="ask",
            execution_entry_status="executable",
            readiness="READY",
            execution_status="executable",
            is_executable=True,
            status="READY",
        ),
    ]
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, rows)

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(tmp_path / "suggestions.jsonl"))
    monkeypatch.setattr(advisory_schema, "logs_dir", lambda: logs_root)

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert list(df_live["advisory_id"]) == ["T-GOOD"]
    payload = json.loads((logs_root / "advisory_schema_errors.jsonl").read_text().strip())
    assert payload["source"] == "dashboard.advisory_snapshot"
    assert payload["trade_id"] == "T-BAD"


def test_load_live_suggestions_df_preserves_canonical_advisory_fields(tmp_path, monkeypatch):
    row = {
        "trade_id": "T-CANONICAL",
        "strategy_id": "CORE",
        "advisory_id": "ADV-1",
        "timestamp": _iso_now(),
        "last_seen_ts": _iso_now(),
        "symbol": "NIFTY",
        "instrument_type": "OPT",
        "strategy_name": "CORE",
        "execution_entry": 72.5,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "display_entry": 72.5,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "entry_reason": "display_from_ask",
        "entry_clear_reason": None,
        "entry": 72.5,
        "entry_status": "displayable",
        "stop": 62.5,
        "stop_loss": 62.5,
        "target": 82.5,
        "row_kind": CANONICAL_ROW_KIND,
        "non_canonical_levels": False,
        "confidence": 0.71,
        "confidence_base": 0.82,
        "confidence_raw": 0.82,
        "confidence_penalty": 0.11,
        "confidence_penalty_total": 0.11,
        "confidence_penalty_reasons": ["STALE_OPTION_LTP"],
        "confidence_final": 0.71,
        "readiness": "READY",
        "hard_blockers": [],
        "soft_penalties": ["STALE_OPTION_LTP"],
        "warnings": ["NO_LIVE_OPTION_FEED"],
        "blockers": ["STALE_OPTION_LTP", "NO_LIVE_OPTION_FEED"],
        "quote_source": "tick_store",
        "quote_age_sec": 4.2,
        "advisory_visible": True,
        "is_executable": True,
        "execution_status": "executable",
        "entry_source": "ask",
        "permission": "EXECUTE",
        "current_ltp": 72.5,
        "decision_explain": [{"code": "TRACE", "message": "kept"}],
        "market_open": True,
    }
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, [row])

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(tmp_path / "suggestions.jsonl"))

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
    assert str(loaded["execution_status"]) == "executable"
    assert str(loaded["entry_source"]) == "ask"
    assert str(loaded["display_entry_status"]) == "displayable"
    assert loaded["decision_explain"] == [{"code": "TRACE", "message": "kept"}]
    assert bool(loaded["market_open"]) is True


def test_dashboard_table_model_includes_new_diagnostic_fields():
    for field in (
        "rejection_impact_warning",
        "starvation_warning",
        "edge_improved_flag",
        "filtering_without_edge_flag",
        "top_damaging_gate_rank",
    ):
        assert field in CANONICAL_COLUMNS


def test_dashboard_table_model_includes_tuning_recommendation_fields():
    for field in (
        "recommended_threshold_delta",
        "gate_protected_flag",
    ):
        assert field in CANONICAL_COLUMNS


def test_dashboard_table_model_includes_triage_fields():
    for field in (
        "triage_recommendation",
        "edge_preserve_flag",
    ):
        assert field in CANONICAL_COLUMNS


def test_dashboard_table_model_includes_stage_authority_policy_fields():
    for field in (
        "stage_authority_warning",
        "effective_session_policy",
        "effective_regime_policy",
        "effective_risk_policy",
        "effective_family_survival_policy",
    ):
        assert field in CANONICAL_COLUMNS


def test_dashboard_table_model_includes_density_fields():
    for field in (
        "trade_density_limit_applied",
        "density_policy_name",
        "density_reject_reason",
    ):
        assert field in CANONICAL_COLUMNS


def test_load_live_suggestions_df_filters_queue_only_row_when_entry_missing(tmp_path, monkeypatch):
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
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, [row])

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(tmp_path / "suggestions.jsonl"))

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert df_live.empty


def test_dashboard_view_matches_engine_row_after_recovery(tmp_path, monkeypatch):
    now_ts = _iso_now()
    stale_row = {
        "trade_id": "T-RECOVER",
        "strategy_id": "CORE",
        "advisory_id": "ADV-RECOVER",
        "timestamp": now_ts,
        "last_seen_ts": now_ts,
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
        "timestamp": now_ts,
        "last_seen_ts": now_ts,
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
        "stop": 63.0,
        "stop_loss": 63.0,
        "target": 83.0,
        "row_kind": CANONICAL_ROW_KIND,
        "non_canonical_levels": False,
        "confidence": 0.62,
        "confidence_raw": 0.62,
        "confidence_penalty": 0.0,
        "confidence_final": 0.62,
        "readiness": "READY",
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
        "blockers": [],
        "quote_source": "tick_store",
        "quote_age_sec": 1.2,
        "advisory_visible": True,
        "is_executable": True,
        "execution_status": "executable",
        "entry_source": "ask",
        "permission": "EXECUTE",
        "freshness_reason": "quote_within_threshold",
        "freshness_market_open": True,
        "decision_explain": [],
        "market_open": True,
    }
    advisory_snapshot_path = _write_advisory_snapshot(tmp_path, [stale_row, fresh_row])

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)
    monkeypatch.setattr(runtime, "canonical_suggestions_log_path", lambda: str(tmp_path / "suggestions.jsonl"))

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert len(df_live) == 1
    loaded = df_live.iloc[0]
    assert loaded["trade_id"] == "T-RECOVER"
    assert float(loaded["entry"]) == 73.0
    assert loaded["readiness"] == "READY"
    assert loaded["execution_status"] == "executable"
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


def test_select_executable_suggestion_rows_excludes_queue_only_non_executable_row():
    df = pd.DataFrame(
        [
            {
                "trade_id": "T-QUEUE",
                "status": "QUEUE_ONLY",
                "readiness": "QUEUE_ONLY",
                "execution_status": "queue_only",
                "entry": 72.5,
                "entry_status": "non_executable",
                "entry_source": "mark",
                "execution_entry": None,
                "execution_entry_status": "non_executable",
                "execution_entry_source": "none",
                "hard_blockers": [],
                "last_seen_ts": _iso_now(),
            }
        ]
    )

    out = runtime._select_executable_suggestion_rows(df)

    assert out.empty


def test_select_executable_suggestion_rows_excludes_invalid_or_blocked_rows():
    df = pd.DataFrame(
        [
            {
                "trade_id": "T-INVALID",
                "status": "INVALID",
                "readiness": "BLOCKED",
                "execution_status": "blocked",
                "entry": 72.5,
                "entry_status": "displayable",
                "entry_source": "ask",
                "execution_entry": 72.5,
                "execution_entry_status": "executable",
                "execution_entry_source": "ask",
                "hard_blockers": ["NO_LIVE_OPTION_FEED"],
                "last_seen_ts": _iso_now(),
            }
        ]
    )

    out = runtime._select_executable_suggestion_rows(df)

    assert out.empty


def test_select_executable_suggestion_rows_keeps_ready_executable_row():
    df = pd.DataFrame(
        [
            {
                "trade_id": "T-READY",
                "status": "READY",
                "readiness": "READY",
                "execution_status": "executable",
                "entry": 73.0,
                "entry_status": "displayable",
                "entry_source": "ask",
                "execution_entry": 73.0,
                "execution_entry_status": "executable",
                "execution_entry_source": "ask",
                "hard_blockers": [],
                "last_seen_ts": _iso_now(),
            }
        ]
    )

    out = runtime._select_executable_suggestion_rows(df)

    assert list(out["trade_id"]) == ["T-READY"]


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
