import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import model_registry


def main():
    parser = argparse.ArgumentParser(description="Rollback model to previous or specified version.")
    parser.add_argument("--family", default="xgb")
    parser.add_argument("--to", default="previous", help="previous or version hash")
    args = parser.parse_args()

    if args.to == "previous":
        prev = model_registry.rollback_model(args.family)
        if not prev:
            raise SystemExit("No previous model available.")
        print(f"Rolled back to: {prev}")
        return

    models = model_registry.list_models(args.family)
    match = None
    for m in models:
        if m.get("hash") == args.to or m.get("path") == args.to:
            match = m
            break
    if not match:
        raise SystemExit("Model hash/path not found in registry.")
    model_registry.activate_model(args.family, match["path"])
    print(f"Activated model: {match['path']}")


if __name__ == "__main__":
    main()
