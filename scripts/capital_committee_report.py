import argparse
import json
from pathlib import Path

from core.capital_allocator import compute_desk_budgets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    args = parser.parse_args()

    report = compute_desk_budgets(days=args.days)
    report["days"] = args.days
    out = Path("logs/capital_committee_report.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Capital committee report: {out}")


if __name__ == "__main__":
    main()
