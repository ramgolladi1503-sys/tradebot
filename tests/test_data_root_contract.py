import importlib

from config import config as cfg
from core import approval_store
import core.runtime_paths as runtime_paths


def test_data_root_contract_for_approval_store(monkeypatch, tmp_path):
    custom_data_root = tmp_path / "runtime-state"
    monkeypatch.setenv("DATA_ROOT", str(custom_data_root))
    importlib.reload(runtime_paths)

    assert runtime_paths.DATA_ROOT == custom_data_root
    assert not runtime_paths.DATA_ROOT.exists()

    trade_db = runtime_paths.DESKS_ROOT / "DEFAULT" / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(trade_db), raising=False)

    approval_store.init_db()

    assert trade_db.parent.exists()
    assert trade_db.exists()
