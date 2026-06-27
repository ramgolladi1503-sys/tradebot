from enum import Enum, auto

class ResearchStage(Enum):
    """
    Lifecycle of a research idea/experiment from inception to certification.
    Must always progress forward or fall back explicitly.
    IDEA -> HYPOTHESIS -> DESIGN -> IMPLEMENTED -> TESTED -> FAILED | PAPER_READY -> SHADOW_READY -> STRATEGY_REGISTRY
    """
    IDEA = auto()
    HYPOTHESIS = auto()
    DESIGN = auto()
    IMPLEMENTED = auto()
    TESTED = auto()
    FAILED = auto()
    PAPER_READY = auto()
    SHADOW_READY = auto()
    STRATEGY_REGISTRY = auto()


class PromotionStatus(Enum):
    """
    Recommendations provided by the promotion policy engine.
    """
    KEEP_RESEARCH = auto()
    REQUIRES_MORE_DATA = auto()
    READY_FOR_IMPLEMENTATION = auto()
    READY_FOR_STRATEGY_REGISTRY = auto()
    DO_NOT_PROMOTE = auto()
