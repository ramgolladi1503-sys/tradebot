from core.research_registry.research_models import ExperimentVersion, PromotionRecommendation
from core.research_registry.research_types import PromotionStatus, ResearchStage


class PromotionPolicy:
    """Legacy registry recommendation policy.

    This registry is descriptive lineage infrastructure, not research authority.
    It may recommend pre-evidence engineering transitions, but it MUST NOT
    authorize PAPER_READY, SHADOW_READY, or STRATEGY_REGISTRY. Those states
    require the governed, hash-pinned research/certification path.
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
                status = PromotionStatus.REQUIRES_MORE_DATA
                reasons.append(
                    "Legacy TESTED status cannot authorize PAPER_READY; governed "
                    "hash-pinned validation evidence is required."
                )

        elif version.stage == ResearchStage.PAPER_READY:
            status = PromotionStatus.REQUIRES_MORE_DATA
            reasons.append(
                "Legacy PAPER_READY status cannot authorize SHADOW_READY; governed "
                "authority evidence is required."
            )

        elif version.stage == ResearchStage.SHADOW_READY:
            status = PromotionStatus.REQUIRES_MORE_DATA
            reasons.append(
                "Legacy SHADOW_READY status cannot authorize STRATEGY_REGISTRY; "
                "governed authority evidence is required."
            )

        elif version.stage == ResearchStage.FAILED:
            status = PromotionStatus.DO_NOT_PROMOTE
            reasons.append("Experiment has failed.")

        elif version.stage == ResearchStage.STRATEGY_REGISTRY:
            status = PromotionStatus.KEEP_RESEARCH
            reasons.append(
                "Experiment is recorded in the legacy Strategy Registry; this is "
                "not evidence of structural edge or execution authority."
            )

        return PromotionRecommendation(status=status, reasons=reasons, target_stage=target)
