from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_status_runtime_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "status_runtime.py"
    spec = importlib.util.spec_from_file_location("status_runtime", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_status_runtime_report_reads_runtime_files(tmp_path):
    module = _load_status_runtime_module()
    runtime_logs = tmp_path / ".runtime" / "logs"
    runtime_logs.mkdir(parents=True, exist_ok=True)
    process_logs = tmp_path / "logs"
    process_logs.mkdir(parents=True, exist_ok=True)
    (runtime_logs / "suggestions_status.json").write_text(
        json.dumps(
            {
                "market_mode": "OFFHOURS",
                "market_open": False,
                "status": "market_closed",
                "suggestion_count": 0,
                "primary_blocker": "MARKET_CLOSED",
                "latest_trade_id": "T-1",
                "latest_entry_status": "NO_LIVE_OPTION_FEED",
                "latest_permission": "BLOCK",
            }
        )
    )
    (runtime_logs / "engine_cycle_status.json").write_text(
        json.dumps(
            {
                "cycle_ok": True,
                "cycle_stage": "market_closed",
                "market_mode": "OFFHOURS",
                "market_open": False,
                "candidates_seen": 0,
                "candidates_blocked": 1,
                "candidates_enqueued": 0,
                "primary_blocker": "MARKET_CLOSED",
                "reason": "MARKET_CLOSED",
                "subreason": "",
            }
        )
    )
    (runtime_logs / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "ws_connected": True,
                "subscribed_option_tokens_count": 70,
                "missing_option_tokens_count": 0,
            }
        )
    )

    report = module.build_status_report(root=tmp_path, runtime_logs=runtime_logs)

    assert report["market_mode"] == "OFFHOURS"
    assert report["suggestions"]["primary_blocker"] == "MARKET_CLOSED"
    assert report["engine"]["primary_blocker"] == "MARKET_CLOSED"
    assert report["feed"]["subscribed_option_tokens_count"] == 70
    rendered = module.render_status_report(report)
    assert "market_closed" in rendered
    assert "MARKET_CLOSED" in rendered
    assert "ws_connected=True" in rendered
    assert "stage=market_closed" in rendered
    assert "reason=MARKET_CLOSED" in rendered
