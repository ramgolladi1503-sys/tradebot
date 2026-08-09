import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts" / "research" / "hypothesis_factory" / "audit_corpus_source_conflicts.py"
spec = importlib.util.spec_from_file_location("audit_corpus_source_conflicts", PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_conflict_audit_distinguishes_agreement_and_conflict(tmp_path):
    path = tmp_path / "banknifty.csv"
    rows = [
        {"timestamp":"2026-01-01T09:15:00","instrument":"BANKNIFTY","open":"100","high":"101","low":"99","close":"100.5","source_path":"A"},
        {"timestamp":"2026-01-01T09:15:00","instrument":"BANKNIFTY","open":"100","high":"101","low":"99","close":"100.5","source_path":"B"},
        {"timestamp":"2026-01-01T09:16:00","instrument":"BANKNIFTY","open":"101","high":"102","low":"100","close":"101.5","source_path":"A"},
        {"timestamp":"2026-01-01T09:16:00","instrument":"BANKNIFTY","open":"101","high":"103","low":"100","close":"102.0","source_path":"B"},
        {"timestamp":"2026-01-01T09:17:00","instrument":"BANKNIFTY","open":"102","high":"103","low":"101","close":"102.5","source_path":"A"},
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)

    result = mod.analyze(path)
    assert result["agreeing_overlap_groups"] == 1
    assert result["conflict_groups"] == 1
    assert result["exclusive_timestamp_groups"] == 1
    assert result["authority"]["data_source_selection"] == "NOT_DECIDED"
    assert result["authority"]["runtime_authority"] == "NONE"
