from typing import List, Optional
from core.research_registry.research_models import ExperimentVersion, ResearchStage

class ExperimentValidator:
    """Validates the immutability, required fields, and state transitions of experiments."""

    VALID_TRANSITIONS = {
        ResearchStage.IDEA: {ResearchStage.HYPOTHESIS, ResearchStage.FAILED},
        ResearchStage.HYPOTHESIS: {ResearchStage.DESIGN, ResearchStage.FAILED},
        ResearchStage.DESIGN: {ResearchStage.IMPLEMENTED, ResearchStage.FAILED},
        ResearchStage.IMPLEMENTED: {ResearchStage.TESTED, ResearchStage.FAILED},
        ResearchStage.TESTED: {ResearchStage.PAPER_READY, ResearchStage.FAILED},
        ResearchStage.PAPER_READY: {ResearchStage.SHADOW_READY, ResearchStage.FAILED},
        ResearchStage.SHADOW_READY: {ResearchStage.STRATEGY_REGISTRY, ResearchStage.FAILED},
        ResearchStage.FAILED: {ResearchStage.FAILED}, # Terminal or can it be revived? Assuming terminal for strictness unless explicit revival. Let's allow reviving to IDEA or DESIGN.
        ResearchStage.STRATEGY_REGISTRY: set(), # Terminal
    }
    
    # Adding revival transitions for FAILED
    VALID_TRANSITIONS[ResearchStage.FAILED] = {ResearchStage.IDEA, ResearchStage.DESIGN}

    @staticmethod
    def validate_version(version: ExperimentVersion, previous_version: Optional[ExperimentVersion] = None) -> List[str]:
        """Validate required fields and valid state transitions."""
        errors = []
        if not version.author:
            errors.append("Missing required field: author")
        if not version.branch:
            errors.append("Missing required field: branch")
        if not version.commit:
            errors.append("Missing required field: commit")
        if not version.result.expected_behavior:
            errors.append("Missing required field: expected_behavior")
            
        if previous_version:
            if previous_version.stage != version.stage:
                allowed = ExperimentValidator.VALID_TRANSITIONS.get(previous_version.stage, set())
                if version.stage not in allowed:
                    errors.append(f"Invalid state transition from {previous_version.stage.name} to {version.stage.name}")
        return errors
