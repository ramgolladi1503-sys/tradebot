import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "scripts" / "research" / "hypothesis_factory" / "build_corpus_cache.py"
SCREEN_PATH = ROOT / "scripts" / "research" / "hypothesis_factory" / "run_cached_screen.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cache = load("build_corpus_cache_test", CACHE_PATH)
screen = load("run_cached_screen_test", SCREEN_PATH)


def test_cached_screen_uses_canonical_cache_and_stays_research_only(tmp_path):
    corpus = tmp_path / "banknifty.csv"
    rows = ["timestamp,instrument,open,high,low,close,volume,is_fallback"]
    for day in range(1, 25):
        for bar in range(8):
            px = 100 + day + bar
            rows.append(f"2026-01-{day:02d}T09:{15+bar:02d}:00,BANKNIFTY,{px},{px+1},{px-1},{px+0.5},1000,false")
    corpus.write_text("\n".join(rows) + "\n", encoding="utf-8")

    args = cache.parser().parse_args([
        "--no-known-roots", "--no-gdrive-discovery",
        "--corpus-root", str(corpus),
        "--cache-dir", str(tmp_path / "cache"),
        "--instrument", "BANKNIFTY",
        "--progress-every", "0",
    ])
    args.instrument = ["BANKNIFTY"]
    built = cache.build(args)
    assert built["canonical_rows"] > 0

    rc = screen.main([
        "--cache-dir", str(tmp_path / "cache"),
        "--instrument", "BANKNIFTY",
        "--output-dir", str(tmp_path / "runs"),
        "--run-id", "TEST-CACHED",
        "--min-trades", "1",
        "--cost-bps", "0",
    ])
    assert rc == 0
    manifest = json.loads((tmp_path / "runs" / "TEST-CACHED" / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["loaded_rows"] > 0
    assert manifest["runtime_authority"] == "NONE"
    assert manifest["broker_actions_allowed"] is False
    assert manifest["certification"] == "NOT_CERTIFIED"
