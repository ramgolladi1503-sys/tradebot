import argparse
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.replay_engine import ReplayEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--speed", type=float, default=50.0)
    parser.add_argument("--symbols", default="NIFTY,SENSEX")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--db", default="", help="Optional SQLite db path")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    db_path = Path(args.db) if args.db else None
    engine = ReplayEngine(db_path=db_path, seed=args.seed)
    out = engine.replay_day(args.date, symbols, speed=args.speed)
    print(f"Replay complete: {out}")


if __name__ == "__main__":
    main()
