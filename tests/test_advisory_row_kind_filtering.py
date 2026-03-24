from __future__ import annotations

import json
from datetime import datetime, timezone

import dashboard.streamlit_app_runtime as runtime
from core import advisory_schema
from core.advisory_row_integrity import BLOCKED_DEBUG_ROW_KIND, CANONICAL_ROW_KIND


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_row(trade_id: str, *, row_kind: str, stop_loss: float | None, target: float | None) -> dict:
    return advisory_schema.serialize_advisory_row(
        {
            "trade_id": trade_id,
            "advisory_id": trade_id,
            "strategy_id": "CORE",
            "strategy_name": "CORE",
            "symbol": "NIFTY",
            "instrument_type": "OPT",
            "instrument": "OPT",
            "timestamp": _iso_now(),
            "status": "ADVISORY_ONLY",
            "permission": "ADVISORY_ONLY",
            "readiness": "ADVISORY_ONLY",
            "execution_status": "advisory_only",
            "execution_entry": None,
            "execution_entry_source": "none",
            "execution_entry_status": "non_executable",
            "display_entry": 120.0,
            "display_entry_source": "last",
            "display_entry_status": "displayable",
            "entry_reason": "display_from_last",
            "entry_clear_reason": None,
            "entry": 120.0,
            "entry_status": "displayable",
            "entry_source": "last",
            "confidence": 0.6,
            "blockers": [],
            "hard_blockers": [],
            "soft_penalties": [],
            "warnings": [],
            "quote_source": "tick_store",
            "quote_age_sec": 1.0,
            "decision_explain": [],
            "market_open": False,
            "side": "BUY",
            "row_kind": row_kind,
            "non_canonical_levels": row_kind != CANONICAL_ROW_KIND,
            "stop": stop_loss,
            "stop_loss": stop_loss,
            "target": target,
        },
        allow_legacy=True,
    )


def test_load_live_suggestions_df_filters_out_non_canonical_rows(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    advisory_snapshot_path = runtime_root / "advisory_latest.json"
    rows = [
        _snapshot_row("T-CANONICAL", row_kind=CANONICAL_ROW_KIND, stop_loss=100.0, target=150.0),
        _snapshot_row("T-BLOCKED", row_kind=BLOCKED_DEBUG_ROW_KIND, stop_loss=None, target=None),
    ]
    advisory_snapshot_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": _iso_now(), "producer": "test", "payload": {"rows": rows}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime, "ADVISORY_LATEST_PATH", advisory_snapshot_path)

    df_live = runtime._load_live_suggestions_df(limit=10)

    assert list(df_live["trade_id"]) == ["T-CANONICAL"]
    assert df_live.iloc[0]["row_kind"] == CANONICAL_ROW_KIND
