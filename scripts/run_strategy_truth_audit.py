import argparse
import sys
import json
import dataclasses
from core.strategy_truth.audit_engine import AuditEngine
from core.strategy_truth.report_generator import ReportGenerator


def _default_serializer(obj):
    if hasattr(obj, "value"): # Enums
        return obj.value
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def main():
    parser = argparse.ArgumentParser(description="Run the Strategy Truth Engine.")
    parser.add_argument("--strategy", type=str, help="Audit a specific strategy ID")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")
    args = parser.parse_args()

    try:
        engine = AuditEngine()
        summary = engine.run_all(target_strategy_id=args.strategy)

        # Generate Reports
        generator = ReportGenerator()
        generator.write_reports(summary)

        if args.json:
            print(json.dumps(dataclasses.asdict(summary), default=_default_serializer, indent=2))
        else:
            print("=" * 40)
            print("Strategy Truth Engine Summary")
            print("=" * 40)
            print(f"Total Strategies Evaluated: {summary.total_strategies}")
            print(f"Fully Verified: {summary.fully_verified_count}")
            print(f"Partially Verified: {summary.partially_verified_count}")
            print(f"Implementation Mismatch: {summary.mismatch_count}")
            print(f"Registry Incomplete: {summary.registry_incomplete_count}")
            print("=" * 40)
            print("Detailed markdown reports generated in docs/strategy_truth/")
            print("Done.")

        sys.exit(0)

    except Exception as e:
        print(f"Tool failure: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
