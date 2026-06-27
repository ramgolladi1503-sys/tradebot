from typing import Optional
from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_certification.certification_models import GateResult
from core.strategy_certification.certification_types import GateStatus

class RegistryGate:
    """
    Gate 1 - Registry

    Verify:
    - registry entry exists
    - version exists
    - hypothesis documented
    - metadata complete

    Failure: RESEARCH_ONLY
    """
    
    @staticmethod
    def evaluate(manifest: Optional[StrategyManifest]) -> GateResult:
        if manifest is None:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Registry entry does not exist or could not be loaded.",
                blockers=["Missing StrategyManifest"]
            )
            
        contract = manifest.contract
        
        missing_fields = []
        if not contract.strategy_id:
            missing_fields.append("strategy_id")
        if not contract.version:
            missing_fields.append("version")
        if not contract.market_hypothesis:
            missing_fields.append("market_hypothesis")
            
        # StrategyManifest validate() already checks metadata completeness, 
        # but we do a gentle check here to surface it as a gate failure rather than a crash.
        
        if missing_fields:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Metadata incomplete or missing.",
                blockers=[f"Missing fields: {', '.join(missing_fields)}"]
            )
            
        return GateResult(
            status=GateStatus.PASS,
            reason="Registry entry is complete and valid.",
        )
