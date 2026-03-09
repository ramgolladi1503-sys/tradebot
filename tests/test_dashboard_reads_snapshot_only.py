from __future__ import annotations

import json

from config import config as cfg
from dashboard.loaders import load_feed_state


def test_dashboard_feed_loader_uses_snapshot_freshness_only(tmp_path, monkeypatch):
    desk = "DEFAULT"
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    desk_logs = logs_root / "desks" / desk
    desk_logs.mkdir(parents=True, exist_ok=True)

    runtime_health_path = desk_logs / "runtime_health_latest.json"
    snapshot_path = desk_logs / "market_snapshot_latest.json"

    snapshot = {
        "schema_version": "1.0",
        "snapshot_id": "snap-dashboard-001",
        "timestamp_epoch": 1_772_400_000.0,
        "symbol": "NIFTY",
        "token_coverage": {
            "index_token": 256265,
            "option_tokens_count": 60,
        },
        "freshness": {
            "max_tick_age_sec": 1.2,
            "sla_threshold_sec": 2.5,
            "stale_tokens_count": 0,
        },
        "data_sources": {
            "ticks": "sqlite",
            "token_resolution": "resolver",
        },
    }
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    runtime_health_path.write_text(
        json.dumps(
            {
                "feed": {"ws_connected": True},
                "db_ok": True,
                "snapshot_path": str(snapshot_path),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "DESKS_ROOT", str(runtime_root / "desks"), raising=False)

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("freshness recomputation must not be called in dashboard loader")

    monkeypatch.setattr("core.freshness_sla.get_freshness_status", _forbidden)

    vm = load_feed_state(desk)
    assert vm.status == "ok"
    assert vm.payload.get("freshness_source") == "snapshot_v1"
    freshness = vm.payload.get("freshness") or {}
    assert freshness.get("max_tick_age_sec") == 1.2
    assert freshness.get("sla_threshold_sec") == 2.5
    runtime_eval = vm.payload.get("runtime_health") or {}
    assert runtime_eval.get("ok") is True
