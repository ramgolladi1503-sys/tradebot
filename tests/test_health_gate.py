from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

from config import config as cfg
from core.events import read_events
from core.health_gate import run_health_gate


def test_health_gate_golden_path_writes_events_and_recon(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    db_path = runtime_root / "db" / "DEFAULT.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)

    report = run_health_gate(desk="DEFAULT", strict=True, run_id="HG_TEST_RUN")
    assert report["exit_code"] == 0

    events = read_events(run_id="HG_TEST_RUN")
    assert events
    assert sum(1 for e in events if e.get("type") == "trade_intent_created") == 1
    assert sum(1 for e in events if e.get("type") == "order_submitted") == 1
    assert sum(1 for e in events if e.get("type") == "fill") == 1

    recon_path = logs_root / "recon.json"
    assert recon_path.exists()
    recon = json.loads(recon_path.read_text(encoding="utf-8"))
    assert int(recon.get("trade_count") or 0) == 1


def test_health_gate_blocks_live_arming_on_p0(monkeypatch):
    import scripts.arm_trade as arm_trade

    importlib.reload(arm_trade)

    called = {"arm": False}

    class _FakeScorecard:
        def run(self, desk_id: str):
            del desk_id
            return {
                "status": "FAIL",
                "report_json_path": "/tmp/go_live_scorecard.json",
                "report_md_path": "/tmp/go_live_scorecard.md",
                "failures": [{"code": "HEALTH_GATE_STRICT_P0"}],
            }

    def _fake_scorecard_factory():
        return _FakeScorecard()

    def _fake_arm(*args, **kwargs):
        called["arm"] = True
        return True, "approval_armed"
    monkeypatch.setattr(arm_trade, "GoLiveScorecard", _fake_scorecard_factory)
    monkeypatch.setattr(arm_trade, "arm_order_intent", _fake_arm)

    argv = ["arm_trade.py", "--payload-hash", "deadbeef"]
    monkeypatch.setattr(sys, "argv", argv)

    code = arm_trade.main()
    assert code == 2
    assert called["arm"] is False


def test_no_hardcoded_logs_or_data_paths():
    root = Path(__file__).resolve().parents[1]
    target_files = []
    target_files.extend(sorted((root / "dashboard").rglob("*.py")))
    target_files.extend(
        [
            root / "scripts" / "arm_trade.py",
            root / "scripts" / "reconcile_fills.py",
            root / "scripts" / "run_execution_analytics.py",
            root / "core" / "events.py",
            root / "core" / "health_scenarios.py",
            root / "core" / "feed" / "sim_feed.py",
            root / "core" / "broker" / "mock_broker.py",
            root / "core" / "reconciliation_project_from_events.py",
            root / "dashboard" / "loader_adapters.py",
        ]
    )

    forbidden = (
        'Path("logs/',
        "Path('logs/",
        'pathlib.Path("logs/',
        "pathlib.Path('logs/",
        'Path("data/',
        "Path('data/",
        'pathlib.Path("data/',
        "pathlib.Path('data/",
    )
    allow_hints = (
        "logs_dir(",
        "cfg.TRADE_DB_PATH",
        "resolve_trade_log_path(",
        "ensure_trade_log_file(",
        "core.paths.",
        "# ALLOW_HARDCODE_PATH",
    )

    violations = []
    for file_path in [p for p in target_files if p.exists()]:
        in_doc = False
        delim = None
        for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()

            if in_doc:
                if delim in line and line.count(delim) % 2 == 1:
                    in_doc = False
                    delim = None
                continue

            if stripped.startswith("#"):
                continue

            for candidate in ("'''", '"""'):
                if candidate in line and line.count(candidate) % 2 == 1:
                    in_doc = True
                    delim = candidate
                    break
            if in_doc:
                continue

            if any(h in line for h in allow_hints):
                continue
            if any(f in line for f in forbidden):
                violations.append((str(file_path.relative_to(root)), line_no, stripped[:180]))

    assert not violations, "\n".join(
        ["Hardcoded logs/data paths detected in guarded files:"]
        + [f"- {path}:{line_no}: {text}" for path, line_no, text in violations]
    )
