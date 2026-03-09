#!/usr/bin/env python
import argparse
import json

import core.feed_restart_guard as restart_guard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--yes-i-mean-it",
        action="store_true",
        help="Required to clear feed restart guard state.",
    )
    args = parser.parse_args()
    if not args.yes_i_mean_it:
        raise SystemExit("Refusing to clear feed restart guard without --yes-i-mean-it")

    state_path = restart_guard.STATE_PATH
    before = {}
    if state_path.exists():
        try:
            before = json.loads(state_path.read_text())
        except Exception:
            before = {"state": "unreadable"}
    print(f"Feed restart guard before: {before}")

    restart_guard.feed_restart_guard.reset(reason="manual_clear")

    after = {}
    if state_path.exists():
        try:
            after = json.loads(state_path.read_text())
        except Exception:
            after = {"state": "unreadable"}
    print(f"Feed restart guard after: {after}")


if __name__ == "__main__":
    main()
