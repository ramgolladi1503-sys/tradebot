from typing import List
from core.strategy_truth.truth_models import DependencyFinding, StrategySourceEvidence
from core.strategy_registry.strategy_contract import StrategyContract


class DependencyAnalyzer:
    """Analyzes dependencies for a strategy."""

    def __init__(self, contract: StrategyContract, source_evidence: StrategySourceEvidence):
        self.contract = contract
        self.source_evidence = source_evidence

    def analyze(self) -> List[DependencyFinding]:
        findings = []

        # 1. Analyze imported modules for direct coupling
        for mod in self.source_evidence.imported_modules:
            if "execution" in mod or "broker" in mod or "order" in mod:
                findings.append(
                    DependencyFinding(
                        dependency_name=mod,
                        dependency_type="execution",
                        is_direct_coupling=True,
                        reason="Direct execution coupling detected in imports.",
                    )
                )
            if "ranking" in mod:
                findings.append(
                    DependencyFinding(
                        dependency_name=mod,
                        dependency_type="ranking",
                        is_direct_coupling=True,
                        reason="Direct ranking coupling detected in imports.",
                    )
                )
            if "replay" in mod:
                findings.append(
                    DependencyFinding(
                        dependency_name=mod,
                        dependency_type="replay",
                        is_direct_coupling=True,
                        reason="Direct replay coupling detected in imports.",
                    )
                )
            if "risk" in mod:
                findings.append(
                    DependencyFinding(
                        dependency_name=mod,
                        dependency_type="risk engine",
                        reason="Risk engine dependency found.",
                    )
                )

        # 2. Analyze candidate hooks and execution hooks from AST
        for hook in self.source_evidence.execution_hooks:
            findings.append(
                DependencyFinding(
                    dependency_name=hook,
                    dependency_type="execution hook",
                    is_direct_coupling=True,
                    reason=f"Execution hook '{hook}' detected in implementation.",
                )
            )

        for hook in self.source_evidence.ranking_hooks:
            findings.append(
                DependencyFinding(
                    dependency_name=hook,
                    dependency_type="ranking hook",
                    is_direct_coupling=True,
                    reason=f"Ranking hook '{hook}' detected in implementation.",
                )
            )

        # 3. Check for missing/unused dependencies from contract
        # (This is mostly around indicators and market data. We can let ImplementationAuditor do Indicator status,
        # but here we can check market data and sessions)
        # Assuming we just do a naive check if market data names appear in imports or code
        for req_data in self.contract.required_market_data:
            # Very naive text search fallback
            found = False
            for func in self.source_evidence.functions:
                if req_data.lower() in func.lower():
                    found = True
            for const in self.source_evidence.constants:
                if req_data.lower() in const.lower():
                    found = True
            
            if not found:
                findings.append(
                    DependencyFinding(
                        dependency_name=req_data,
                        dependency_type="market data",
                        is_unused=True,
                        reason=f"Declared required_market_data '{req_data}' not obviously used in code.",
                    )
                )

        return findings
