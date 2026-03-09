from __future__ import annotations

from config import config as cfg
from core.health_scenarios import run_one_trade_can_build


def test_one_trade_can_build_succeeds(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    db_path = runtime_root / "db" / "DEFAULT.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)

    out = run_one_trade_can_build("DEFAULT", run_id="HG_ONE_TRADE")
    assert out.get("ok") is True
    assert str(out.get("final_action")) == "EXECUTE"
    assert out.get("final_blocker") in (None, "", "NONE")
    assert str(out.get("entry_status")) == "OK"
    assert int(out.get("instrument_token") or 0) > 0

