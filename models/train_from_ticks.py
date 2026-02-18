from __future__ import annotations

import argparse

from models.tick_dataset import build_tick_dataset

__all__ = ["build_tick_dataset"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a tick dataset from a sqlite database.")
    parser.add_argument("--db-path", required=True, help="Path to sqlite database containing ticks.")
    parser.add_argument("--horizon", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=0.001)
    parser.add_argument("--out-path", default=None)
    parser.add_argument("--from-depth", action="store_true")
    parser.add_argument("--depth-tolerance-sec", type=float, default=2.0)
    args = parser.parse_args()

    df = build_tick_dataset(
        db_path=args.db_path,
        horizon=args.horizon,
        threshold=args.threshold,
        out_path=args.out_path,
        from_depth=args.from_depth,
        depth_tolerance_sec=args.depth_tolerance_sec,
    )
    print(f"rows={len(df)}")


if __name__ == "__main__":
    main()
