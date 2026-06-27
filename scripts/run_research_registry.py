#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime
from core.research_registry import (
    ResearchEngine, ResearchHypothesis, ResearchExperiment, ExperimentVersion,
    ExperimentResultReference, ParameterSet, MarketUniverse, ResearchStage,
    ReportGenerator
)

def build_mock_data(engine: ResearchEngine):
    hyp = ResearchHypothesis(
        hypothesis_id="HYP-1",
        title="Mean Reversion on SPY",
        description="SPY mean reverts after 3 down days.",
        created_timestamp=datetime.utcnow(),
        author="quant_1"
    )
    engine.register_hypothesis(hyp)

    exp = ResearchExperiment(
        experiment_id="EXP-1",
        parent_hypothesis_id="HYP-1"
    )
    engine.register_experiment(exp)

    v1 = ExperimentVersion(
        version_id="V1",
        created_timestamp=datetime.utcnow(),
        author="quant_1",
        branch="feature/mean-rev",
        commit="a1b2c3d4",
        market_universe=MarketUniverse(dataset="us_eq", market="SPY", timeframe="1D"),
        parameters=ParameterSet(parameters={"down_days": "3"}),
        reason="Initial test",
        result=ExperimentResultReference(
            expected_behavior="Sharpe > 1.5",
            actual_behavior="Tested",
            limitations=["No slippage model"],
            conclusion="Promising"
        ),
        stage=ResearchStage.TESTED
    )
    engine.add_experiment_version("EXP-1", v1)
    engine.evaluate_experiment("EXP-1", "quant_1")

def main():
    engine = ResearchEngine()
    build_mock_data(engine)
    
    report = engine.generate_report_model()
    
    out_dir = Path("docs/research_registry")
    generator = ReportGenerator(out_dir)
    generator.generate(report, engine.hypothesis_registry, engine.experiment_registry)
    
    print("Research Registry reports generated.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
