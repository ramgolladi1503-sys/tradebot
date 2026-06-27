#!/usr/bin/env python3
import sys
from pathlib import Path
from core.research_registry import (
    ResearchEngine, ReportGenerator
)
from core.research_registry.experiment_loader import DiskResearchLoader, ResearchLoaderError

def main():
    engine = ResearchEngine()
    loader = DiskResearchLoader(engine.hypothesis_registry, engine.experiment_registry)
    
    try:
        loader.load_all()
    except ResearchLoaderError as e:
        print(f"Validation Error: {e}")
        return 1
        
    out_dir = Path("docs/research_registry")

    if not engine.hypothesis_registry.list_all() and not engine.experiment_registry.list_all():
        print("No research artifacts were found.")
        # Ensure we don't leave stale cache artifacts that fool the pipeline orchestrator
        if out_dir.exists():
            for f in out_dir.glob("*.md"):
                f.unlink()
        return 0

    # For experiments loaded from disk, we need to ensure decisions are generated if they exist
    # In this new model, we just iterate through experiments and evaluate the latest version
    for exp in engine.experiment_registry.list_all():
        if exp.versions:
            latest_version = max(exp.versions, key=lambda v: v.created_timestamp)
            engine.evaluate_experiment(exp.experiment_id, latest_version.author)

    try:
        report = engine.generate_report_model()
    except ValueError as e:
        print(f"Validation Error: {e}")
        return 1
    
    generator = ReportGenerator(out_dir)
    generator.generate(report, engine.hypothesis_registry, engine.experiment_registry)
    
    print("Research Registry reports generated.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
