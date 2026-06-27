import argparse
import sys
import json
import dataclasses
from core.strategy_pipeline.pipeline_engine import StrategyPipelineEngine
from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.report_generator import ReportGenerator

def _default_serializer(obj):
    if hasattr(obj, "value"): # Enums
        return obj.value
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def main():
    parser = argparse.ArgumentParser(description="Strategy Evaluation Orchestrator")
    parser.add_argument("--strategy", type=str, help="Evaluate a specific strategy ID")
    parser.add_argument("--all", action="store_true", help="Evaluate all strategies")
    parser.add_argument("--reports-only", action="store_true", help="Only generate reports from existing data")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache and force re-evaluation")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")
    parser.add_argument("--markdown", action="store_true", help="Output summary in Markdown format")
    
    args = parser.parse_args()
    
    if not args.strategy and not args.all:
        print("Must specify either --strategy or --all", file=sys.stderr)
        sys.exit(1)
        
    if args.all:
        from core.strategy_registry.strategy_registry import StrategyRegistry
        from core.strategy_registry.registry_loader import RegistryLoader
        registry = StrategyRegistry()
        loader = RegistryLoader(registry)
        loader.load_all()
        strategies = [s.contract.strategy_id for s in registry.get_all_strategies()]
        if not strategies:
            print("Warning: 0 strategies loaded from Strategy Registry.", file=sys.stderr)
    else:
        strategies = [args.strategy]
    
    engine = StrategyPipelineEngine()
    generator = ReportGenerator()
    
    results = []
    
    try:
        for strat in strategies:
            context = PipelineContext(
                strategy_id=strat,
                force_refresh=args.force_refresh,
                run_all=args.all,
                dry_run=args.reports_only
            )
            
            tracker = engine.run(strat, context)
            results.append(tracker)
            
            generator.generate_all(tracker)
            
        if args.json:
            print(json.dumps([dataclasses.asdict(r) for r in results], default=_default_serializer, indent=2))
        else:
            print("=" * 40)
            print("Strategy Evaluation Orchestrator Summary")
            print("=" * 40)
            for r in results:
                print(f"Strategy: {r.strategy_id} | Status: {r.global_state.value}")
            print("=" * 40)
            print("Unified reports generated in docs/strategy_pipeline/")
            
        sys.exit(0)
    except Exception as e:
        print(f"Pipeline failure: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
