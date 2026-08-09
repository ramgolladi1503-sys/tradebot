import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "research" / "hypothesis_factory" / "build_kite_replay_underlying_cache.py"
spec = importlib.util.spec_from_file_location("build_kite_replay_underlying_cache", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_prepare_dataframe_maps_date_column_to_timestamp():
    df = pd.DataFrame({
        "date": ["2026-01-01T09:15:00"],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
    })
    out, source = mod.prepare_dataframe(df)
    assert source == "COLUMN"
    assert "timestamp" in out.columns
    assert str(out.loc[0, "timestamp"]).startswith("2026-01-01")


def test_prepare_dataframe_materializes_datetime_index():
    df = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5]},
        index=pd.to_datetime(["2026-01-01T09:15:00"]),
    )
    out, source = mod.prepare_dataframe(df)
    assert source == "INDEX"
    assert "timestamp" in out.columns
    assert str(out.loc[0, "timestamp"]).startswith("2026-01-01")


def test_prepare_dataframe_fails_closed_without_time():
    df = pd.DataFrame({"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5]})
    out, source = mod.prepare_dataframe(df)
    assert source == "MISSING"
    assert "timestamp" not in out.columns
