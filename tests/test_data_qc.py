from __future__ import annotations

from pathlib import Path

from config import config as cfg
from scripts import data_qc


def test_data_qc_materializes_db_when_missing(monkeypatch, tmp_path):
    db_path = tmp_path / "db" / "DEFAULT.sqlite"
    out_path = tmp_path / "logs" / "data_qc.json"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(data_qc, "OUT", out_path, raising=False)

    payload = data_qc.run_qc()

    assert db_path.exists()
    assert out_path.exists()
    assert payload["status"] == "ok"
    assert payload["db_path"] == str(db_path)
    assert "tables" in payload and isinstance(payload["tables"], list)
