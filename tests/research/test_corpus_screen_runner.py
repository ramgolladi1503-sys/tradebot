import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "research" / "hypothesis_factory" / "run_corpus_screen.py"
spec = importlib.util.spec_from_file_location("run_corpus_screen", MODULE_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def test_corpus_runner_writes_manifest_and_research_only_outputs(tmp_path):
    corpus = tmp_path / "corpus.csv"
    corpus.write_text(
        "timestamp,instrument,open,high,low,close,volume,vwap,bid,ask,is_fallback\n"
        + "\n".join(
            f"2026-01-{day:02d}T09:{15+bar:02d}:00,NIFTY,{100+day+bar},{101+day+bar},{99+day+bar},{100+day+bar},1000,{100+day+bar},{99.99+day+bar},{100.01+day+bar},false"
            for day in range(1, 25)
            for bar in range(8)
        )
        + "\n",
        encoding="utf-8",
    )
    args = runner.build_parser().parse_args([
        "--no-known-roots",
        "--no-gdrive-discovery",
        "--corpus-root", str(corpus),
        "--output-dir", str(tmp_path / "runs"),
        "--run-id", "TEST-RUN",
        "--instrument", "NIFTY",
        "--min-trades", "1",
        "--cost-bps", "0",
        "--top-passports", "3",
    ])
    manifest = runner.run(args)
    out_dir = tmp_path / "runs" / "TEST-RUN"
    assert manifest["runtime_authority"] == "NONE"
    assert manifest["broker_actions_allowed"] is False
    assert manifest["certification"] == "NOT_CERTIFIED"
    assert manifest["loaded_rows"] > 0
    assert (out_dir / "leaderboard.csv").exists()
    passports = json.loads((out_dir / "strategy_passports.json").read_text(encoding="utf-8"))
    assert passports
    assert all(p["certification"] == "NOT_CERTIFIED" for p in passports)
    assert all(p["integration"]["allowed_tradebot_mode"] == "RESEARCH_ONLY" for p in passports)


def test_tick_rows_are_aggregated_to_minute_ohlc(tmp_path):
    corpus = tmp_path / "ticks.csv"
    corpus.write_text(
        "exchange_timestamp,instrument_key,ltp,ltq,best_bid,best_ask,is_fallback\n"
        + "\n".join(
            f"2026-01-{day:02d}T09:{15+bar:02d}:10,NSE_INDEX|NIFTY,{100+day+bar},10,{99.99+day+bar},{100.01+day+bar},false"
            for day in range(1, 25)
            for bar in range(8)
        )
        + "\n",
        encoding="utf-8",
    )
    args = runner.build_parser().parse_args([
        "--no-known-roots",
        "--no-gdrive-discovery",
        "--corpus-root", str(corpus),
        "--output-dir", str(tmp_path / "tick-runs"),
        "--run-id", "TICK-RUN",
        "--instrument", "NIFTY",
        "--min-trades", "1",
        "--cost-bps", "0",
    ])
    manifest = runner.run(args)
    assert manifest["loaded_rows"] > 0
    assert manifest["inventory_summary"]["tick_ohlc_rows"] > 0
    assert manifest["inventory_summary"]["normalized_ohlc_rows"] == 0
