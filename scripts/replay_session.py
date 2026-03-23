import argparse
import json
import re
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.paths import runtime_dir
from core.replay_engine import ReplayEngine


def _safe_label(value: str | None, default: str) -> str:
    text = str(value or "").strip() or default
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text)


def _default_output_path(runtime_root: Path, symbol: str | None, start: str | None, end: str | None) -> Path:
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    symbol_label = _safe_label(symbol, "ALL")
    start_label = _safe_label(start, "START")
    end_label = _safe_label(end, "END")
    return logs_root / f"replay_session_{symbol_label}_{start_label}_{end_label}.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="", help="Runtime root containing logs/ and observability/")
    parser.add_argument("--symbol", default="", help="Optional symbol filter, e.g. NIFTY")
    parser.add_argument("--start", default="", help="Optional start time (ISO-8601 or epoch seconds)")
    parser.add_argument("--end", default="", help="Optional end time (ISO-8601 or epoch seconds)")
    parser.add_argument("--out", default="", help="Optional output path for replay JSON")
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).expanduser() if args.runtime_root else runtime_dir()
    replay = ReplayEngine.replay_runtime_artifacts(
        symbol=args.symbol or None,
        start=args.start or None,
        end=args.end or None,
        runtime_root=runtime_root,
    )

    out_path = Path(args.out).expanduser() if args.out else _default_output_path(
        runtime_root,
        args.symbol or None,
        args.start or None,
        args.end or None,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(replay, indent=2, sort_keys=True), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
