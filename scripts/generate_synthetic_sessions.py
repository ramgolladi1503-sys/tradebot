import argparse
from pathlib import Path

from core.synthetic_market import SyntheticSessionConfig, generate_ohlcv_session, write_ohlcv_csv, write_sqlite_session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--symbols", default="NIFTY", help="Comma-separated symbols")
    parser.add_argument("--regime", default="RANGE", help="TREND/RANGE/EVENT")
    parser.add_argument("--bars", type=int, default=360)
    parser.add_argument("--bar-sec", type=int, default=60)
    parser.add_argument("--start-price", type=float, default=25000.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out-dir", default="data/synthetic_sessions")
    parser.add_argument("--out-db", default="")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    db_path = Path(args.out_db) if args.out_db else None
    if db_path:
        db_path.parent.mkdir(exist_ok=True)

    for sym in symbols:
        cfg = SyntheticSessionConfig(
            symbol=sym,
            date=args.date,
            regime=args.regime,
            start_price=args.start_price,
            bars=args.bars,
            bar_sec=args.bar_sec,
            seed=args.seed,
        )
        bars = generate_ohlcv_session(cfg)
        csv_path = out_dir / f"{args.date}_{sym}_ohlcv.csv"
        write_ohlcv_csv(csv_path, bars)
        if db_path:
            write_sqlite_session(db_path, sym, bars)
        print(f"Generated {len(bars)} bars for {sym}: {csv_path}")

    if db_path:
        print(f"Synthetic SQLite: {db_path}")


if __name__ == "__main__":
    main()
