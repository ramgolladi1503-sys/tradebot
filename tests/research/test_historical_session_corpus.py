import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "scripts" / "research" / "hypothesis_factory" / "index_historical_session_corpus.py"
BUILD_PATH = ROOT / "scripts" / "research" / "hypothesis_factory" / "build_historical_underlying_cache.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


indexer = load("index_historical_session_corpus", INDEX_PATH)
builder = load("build_historical_underlying_cache", BUILD_PATH)


def write_underlying(root: Path, date: str, filename: str, family: str):
    folder = root / date / "underlying"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    compact = date.replace("-", "")
    if path.suffix == ".csv":
        path.write_text(
            "timestamp,instrument,open,high,low,close,volume,is_fallback\n"
            f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}T09:15:00,{family},100,101,99,100.5,10,false\n",
            encoding="utf-8",
        )
    else:
        path.write_bytes(b"placeholder")
    return path


def test_infer_date_supports_compact_and_hyphenated_replay_folders(tmp_path):
    compact = tmp_path / "20240603" / "underlying" / "NIFTY_20240603.parquet"
    hyphenated = tmp_path / "2024-07-16" / "underlying" / "BANKNIFTY.parquet"
    assert indexer.infer_date(compact) == "2024-06-03"
    assert indexer.infer_date(hyphenated) == "2024-07-16"


def test_inventory_reports_actual_per_family_session_coverage(tmp_path):
    root = tmp_path / "tradebot_historical_data"
    write_underlying(root, "20240603", "NSE_INDEX|Nifty_20240603.csv", "NIFTY")
    write_underlying(root, "2024-06-04", "NSE_INDEX|Nifty Bank_20240604.csv", "BANKNIFTY")
    write_underlying(root, "20240605", "BSE_INDEX|SENSEX_20240605.csv", "SENSEX")

    result = indexer.inventory([root])
    assert result["summary"]["sessions"] == 3
    assert result["summary"]["underlying_session_counts"] == {
        "NIFTY": 1,
        "BANKNIFTY": 1,
        "SENSEX": 1,
    }
    assert result["runtime_authority"] == "NONE"
    assert result["broker_actions_allowed"] is False


def test_historical_cache_gate_blocks_insufficient_sessions(tmp_path):
    root = tmp_path / "tradebot_historical_data"
    file_path = write_underlying(root, "2024-06-04", "NSE_INDEX|Nifty Bank_20240604.csv", "BANKNIFTY")
    idx = indexer.inventory([root])
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(idx), encoding="utf-8")

    args = builder.parser().parse_args([
        "--index", str(index_path),
        "--instrument", "BANKNIFTY",
        "--cache-dir", str(tmp_path / "cache"),
        "--min-sessions", "2",
        "--progress-every", "0",
    ])
    result = builder.build(args)
    assert result["status"] == "INSUFFICIENT_SESSION_COVERAGE"
    assert result["session_count"] == 1
    assert result["selected_files"] == 1
    assert file_path.exists()
    assert result["runtime_authority"] == "NONE"


def test_historical_cache_builds_only_selected_underlying_family(tmp_path):
    root = tmp_path / "tradebot_historical_data"
    for date in ("20240603", "2024-06-04"):
        compact = date.replace("-", "")
        write_underlying(root, date, f"NSE_INDEX|Nifty Bank_{compact}.csv", "BANKNIFTY")
        write_underlying(root, date, f"BSE_INDEX|SENSEX_{compact}.csv", "SENSEX")

    idx = indexer.inventory([root])
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(idx), encoding="utf-8")

    args = builder.parser().parse_args([
        "--index", str(index_path),
        "--instrument", "BANKNIFTY",
        "--cache-dir", str(tmp_path / "cache"),
        "--min-sessions", "2",
        "--progress-every", "0",
    ])
    result = builder.build(args)
    assert result["status"] == "CACHE_BUILT"
    assert result["selected_files"] == 2
    assert result["session_count"] == 2
    assert result["canonical_rows"] == 2
    assert "BANKNIFTY" in result["canonical_outputs"]
    assert "SENSEX" not in result["canonical_outputs"]
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["runtime_authority"] == "NONE"