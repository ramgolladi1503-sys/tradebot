from core.research_registry.research_models import ExperimentVersion, PromotionRecommendation
from core.research_registry.research_types import PromotionStatus, ResearchStage


class PromotionPolicy:
    """
    Decides PromotionRecommendation based on evidence.
    Never automatically advances stages, only recommends them.
    """

    @staticmethod
    def evaluate(version: ExperimentVersion) -> PromotionRecommendation:
        reasons = []
        status = PromotionStatus.KEEP_RESEARCH
        target = None
        
        if version.stage == ResearchStage.IDEA:
            if version.result.expected_behavior:
                status = PromotionStatus.READY_FOR_IMPLEMENTATION
                target = ResearchStage.HYPOTHESIS
                reasons.append("Idea has defined expected behavior.")
            else:
                status = PromotionStatus.REQUIRES_MORE_DATA
                reasons.append("Idea lacks expected behavior definition.")
                
        elif version.stage == ResearchStage.HYPOTHESIS:
            status = PromotionStatus.READY_FOR_IMPLEMENTATION
            target = ResearchStage.DESIGN
            reasons.append("Hypothesis can proceed to design.")
            
        elif version.stage == ResearchStage.DESIGN:
            status = PromotionStatus.READY_FOR_IMPLEMENTATION
            target = ResearchStage.IMPLEMENTED
            reasons.append("Design can proceed to implementation.")

        elif version.stage == ResearchStage.IMPLEMENTED:
            status = PromotionStatus.READY_FOR_IMPLEMENTATION
            target = ResearchStage.TESTED
            reasons.append("Implementation can proceed to testing.")

        elif version.stage == ResearchStage.TESTED:
            if "fail" in version.result.conclusion.lower() or version.result.actual_behavior == "failed":
                status = PromotionStatus.DO_NOT_PROMOTE
                target = ResearchStage.FAILED
                reasons.append("Testing failed.")
            else:
                status = PromotionStatus.READY_FOR_IMPLEMENTATION
                target = ResearchStage.PAPER_READY
                reasons.append("Testing passed, ready for paper.")

        elif version.stage == ResearchStage.PAPER_READY:
            status = PromotionStatus.READY_FOR_IMPLEMENTATION
            target = ResearchStage.SHADOW_READY
            reasons.append("Ready for shadow deployment.")

        elif version.stage == ResearchStage.SHADOW_READY:
            status = PromotionStatus.READY_FOR_STRATEGY_REGISTRY
            target = ResearchStage.STRATEGY_REGISTRY
            reasons.append("Shadow testing complete. Ready for strategy registry.")

        elif version.stage == ResearchStage.FAILED:
            status = PromotionStatus.DO_NOT_PROMOTE
            reasons.append("Experiment has failed.")

        elif version.stage == ResearchStage.STRATEGY_REGISTRY:
            status = PromotionStatus.KEEP_RESEARCH
            reasons.append("Experiment is already in Strategy Registry.")

        return PromotionRecommendation(status=status, reasons=reasons, target_stage=target)
