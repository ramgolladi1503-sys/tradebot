# PATCH: Opportunity engine hardening

from core.opportunity_engine import *

# Hard override: prevent fallback candidates from ever being executable

def _is_executable_opportunity(candidate):
    truth = super()._execution_truth(candidate) if hasattr(super(), '_execution_truth') else None
    candidate_class = str(_get_value(candidate, "candidate_class") or "").strip().upper()
    if candidate_class in {"FALLBACK", "ADVISORY_ONLY", "SOFTENED", "SYNTHETIC", "PLANNING_ONLY"}:
        return False
    return bool(_get_value(candidate, "execution_allowed", False) and _get_value(candidate, "tradable", False))
