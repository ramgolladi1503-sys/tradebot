import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path("config/feature_flags.json")
    flags = {}
    if path.exists():
        flags = json.loads(path.read_text())
    flags["CANARY_PERCENT"] = 0
    if args.dry_run:
        print("Would set CANARY_PERCENT=0")
        raise SystemExit(0)
    path.write_text(json.dumps(flags, indent=2))
    print("CANARY_PERCENT set to 0")


if __name__ == "__main__":
    main()
