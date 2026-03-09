from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_live_entries.py"
    spec = importlib.util.spec_from_file_location("check_live_entries", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_check_live_entries_reports_good_and_bad_rows(tmp_path):
    module = _load_module()
    runtime_logs = tmp_path / ".runtime" / "logs"
    runtime_logs.mkdir(parents=True, exist_ok=True)
    suggestions_path = runtime_logs / "suggestions.jsonl"
    (runtime_logs / "suggestions_status.json").write_text(
        json.dumps({"market_mode": "LIVE", "market_open": True}),
        encoding="utf-8",
    )
    (runtime_logs / "engine_cycle_status.json").write_text(
        json.dumps({"market_mode": "LIVE", "market_open": True}),
        encoding="utf-8",
    )
    _write_jsonl(
        suggestions_path,
        [
            {
                "trade_id": "T-GOOD",
                "entry_price": 230.15,
                "expected_entry": 230.15,
                "current_ltp": 230.15,
                "entry_status": "OK",
                "permission": "EXECUTE",
                "permission_reason": "aligned",
                "volume": 5000,
                "oi": 20000,
            },
            {
                "trade_id": "T-BAD",
                "entry_price": 100.99,
                "expected_entry": 100.99,
                "current_ltp": 230.15,
                "entry_status": "PRICE_MISMATCH",
                "permission": "ADVISORY_ONLY",
                "permission_reason": "PRICE_MISMATCH",
                "volume": 5000,
                "oi": 20000,
            },
        ],
    )

    report = module.build_live_entry_report(
        root=tmp_path,
        runtime_logs=runtime_logs,
        suggestions_path=suggestions_path,
        limit=10,
    )

    assert report["market_mode"] == "LIVE"
    assert report["row_count"] == 2
    assert report["rows"][0]["trade_id"] == "T-GOOD"
    assert report["rows"][0]["entry_matches_expected"] is True
    assert report["rows"][0]["entry_matches_current_ltp"] is True
    assert report["rows"][0]["status_ok"] is True
    assert report["rows"][1]["trade_id"] == "T-BAD"
    assert report["rows"][1]["entry_matches_current_ltp"] is False
    assert report["rows"][1]["status_ok"] is False
    rendered = module.render_live_entry_report(report)
    assert "OK  trade_id=T-GOOD" in rendered
    assert "BAD trade_id=T-BAD" in rendered
    assert "PRICE_MISMATCH" in rendered
