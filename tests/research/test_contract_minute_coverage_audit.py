import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "research" / "hypothesis_factory" / "audit_contract_minute_coverage.py"
spec = importlib.util.spec_from_file_location("audit_contract_minute_coverage", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(raw, ts, close, source):
    return {
        "timestamp": ts,
        "instrument": "BANKNIFTY",
        "raw_instrument": raw,
        "open": str(close),
        "high": str(close + 1),
        "low": str(close - 1),
        "close": str(close),
        "source_path": source,
    }


def test_distinct_contracts_same_minute_are_not_conflicts(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(
        "timestamp,instrument,raw_instrument,open,high,low,close,source_path\n"
        "2026-01-01T09:15:00,BANKNIFTY,BANKNIFTY26JAN50000CE,100,101,99,100,a.csv\n"
        "2026-01-01T09:15:00,BANKNIFTY,BANKNIFTY26JAN50100CE,110,111,109,110,a.csv\n",
        encoding="utf-8",
    )
    r = mod.analyze(p)
    assert r["unique_contract_minutes"] == 2
    assert r["conflict_groups"] == 0


def test_same_contract_cross_source_conflict_is_counted(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(
        "timestamp,instrument,raw_instrument,open,high,low,close,source_path\n"
        "2026-01-01T09:15:00,BANKNIFTY,BANKNIFTY26JAN50000CE,100,101,99,100,a.csv\n"
        "2026-01-01T09:15:00,BANKNIFTY,BANKNIFTY26JAN50000CE,101,102,100,101,b.csv\n",
        encoding="utf-8",
    )
    r = mod.analyze(p)
    assert r["unique_contract_minutes"] == 1
    assert r["conflict_groups"] == 1
    assert r["interpretation"]["screening_allowed"] is False
