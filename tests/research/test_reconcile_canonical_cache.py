import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "research" / "hypothesis_factory" / "reconcile_canonical_cache.py"
spec = importlib.util.spec_from_file_location("reconcile_canonical_cache", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(ts, close, source, fallback="false"):
    return {
        "timestamp": ts,
        "instrument": "BANKNIFTY",
        "open": str(close),
        "high": str(close + 1),
        "low": str(close - 1),
        "close": str(close),
        "volume": "100",
        "vwap": str(close),
        "bid": str(close - 0.1),
        "ask": str(close + 0.1),
        "is_fallback": fallback,
        "source_path": source,
    }


def test_identical_cross_source_observation_collapses():
    rows = [
        row("2026-01-01T09:15:00", 100, "a.csv"),
        row("2026-01-01T09:15:00", 100, "b.csv"),
    ]
    out, summary = mod.reconcile_rows(rows)
    assert len(out) == 1
    assert summary["duplicate_rows_removed"] == 1
    assert summary["conflict_groups_excluded"] == 0
    assert "a.csv" in out[0]["source_path"] and "b.csv" in out[0]["source_path"]


def test_conflicting_same_timestamp_fails_closed():
    rows = [
        row("2026-01-01T09:15:00", 100, "a.csv"),
        row("2026-01-01T09:15:00", 101, "b.csv"),
    ]
    out, summary = mod.reconcile_rows(rows)
    assert out == []
    assert summary["conflict_groups_excluded"] == 1
    assert summary["conflict_rows_excluded"] == 2


def test_fallback_rows_are_excluded():
    rows = [row("2026-01-01T09:15:00", 100, "a.csv", fallback="true")]
    out, summary = mod.reconcile_rows(rows)
    assert out == []
    assert summary["fallback_rows_excluded"] == 1
