import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "research" / "hypothesis_factory" / "build_corpus_cache.py"
spec = importlib.util.spec_from_file_location("build_corpus_cache", MODULE_PATH)
cache = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = cache
spec.loader.exec_module(cache)


def make_args(tmp_path, corpus):
    return cache.parser().parse_args([
        "--no-known-roots",
        "--no-gdrive-discovery",
        "--corpus-root", str(corpus),
        "--cache-dir", str(tmp_path / "cache"),
        "--instrument", "BANKNIFTY",
        "--max-files", "10",
        "--progress-every", "0",
    ])


def test_cache_builds_canonical_and_reuses_unchanged_file(tmp_path):
    corpus = tmp_path / "banknifty.csv"
    corpus.write_text(
        "timestamp,instrument,open,high,low,close,volume,is_fallback\n"
        "2026-01-01T09:15:00,BANKNIFTY,100,102,99,101,1000,false\n"
        "2026-01-01T09:16:00,BANKNIFTY,101,103,100,102,1100,false\n",
        encoding="utf-8",
    )
    args = make_args(tmp_path, corpus)
    args.instrument = ["BANKNIFTY"]
    first = cache.build(args)
    assert first["canonical_rows"] == 2
    assert first["files_reparsed"] == 1
    assert first["files_reused"] == 0
    output = Path(first["canonical_outputs"]["BANKNIFTY"]["path"])
    assert output.exists()

    second = cache.build(args)
    assert second["canonical_rows"] == 2
    assert second["files_reused"] == 1
    assert second["files_reparsed"] == 0


def test_cache_excludes_fallback_rows(tmp_path):
    corpus = tmp_path / "mixed.csv"
    corpus.write_text(
        "timestamp,instrument,open,high,low,close,volume,is_fallback\n"
        "2026-01-01T09:15:00,BANKNIFTY,100,102,99,101,1000,false\n"
        "2026-01-01T09:16:00,BANKNIFTY,101,500,1,450,1100,true\n",
        encoding="utf-8",
    )
    args = make_args(tmp_path, corpus)
    args.instrument = ["BANKNIFTY"]
    result = cache.build(args)
    assert result["canonical_rows"] == 1
    assert result["runtime_authority"] == "NONE"
    assert result["broker_actions_allowed"] is False


def test_cache_manifest_is_research_only(tmp_path):
    corpus = tmp_path / "one.csv"
    corpus.write_text(
        "timestamp,instrument,open,high,low,close\n"
        "2026-01-01T09:15:00,BANKNIFTY,100,101,99,100.5\n",
        encoding="utf-8",
    )
    args = make_args(tmp_path, corpus)
    args.instrument = ["BANKNIFTY"]
    result = cache.build(args)
    manifest = json.loads((tmp_path / "cache" / "cache_manifest.json").read_text(encoding="utf-8"))
    assert result["certification"] == "NOT_CERTIFIED"
    assert manifest["runtime_authority"] == "NONE"
    assert manifest["broker_actions_allowed"] is False
