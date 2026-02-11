#!/usr/bin/env python
import argparse
import json

from core import feed_circuit_breaker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes-i-mean-it", action="store_true", help="Required to clear breaker.")
    args = parser.parse_args()
    if not args.yes_i_mean_it:
        raise SystemExit("Refusing to clear feed breaker without --yes-i-mean-it")
    state_path = feed_circuit_breaker.STATE_PATH
    before = {}
    if state_path.exists():
        try:
            before = json.loads(state_path.read_text())
        except Exception:
            before = {"tripped": "unknown"}
    print(f"Feed breaker before: {before}")
    feed_circuit_breaker.clear(reason="manual_clear")
    after = {}
    if state_path.exists():
        try:
            after = json.loads(state_path.read_text())
        except Exception:
            after = {"tripped": "unknown"}
    print(f"Feed breaker after: {after}")


if __name__ == "__main__":
    main()
