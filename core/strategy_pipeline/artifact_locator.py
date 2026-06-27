from pathlib import Path
from typing import Optional

class ArtifactLocator:
    """Finds existing artifacts on disk to enable caching and artifact re-use."""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        
    def locate_research_hypothesis(self, strategy_id: str) -> Optional[Path]:
        path = self.base_dir / "docs" / "research_registry" / "01_hypothesis_inventory.md"
        return path if path.exists() else None
        
    def locate_strategy_contract(self, strategy_id: str) -> Optional[Path]:
        path = self.base_dir / "strategies" / f"{strategy_id}.py"
        return path if path.exists() else None
        
    def locate_truth_report(self, strategy_id: str) -> Optional[Path]:
        path = self.base_dir / "docs" / "strategy_truth" / f"{strategy_id}_truth.md"
        return path if path.exists() else None
        
    def locate_evidence_file(self, strategy_id: str) -> Optional[Path]:
        # Typically evidence files are mapped, but for this mock-like pipeline we can look for any evidence matching
        evidence_dir = self.base_dir / "runtime" / "outcome_evidence"
        if not evidence_dir.exists():
            return None
        # In a real environment, we would look for the specific strategy ID inside the jsonl
        for f in evidence_dir.glob("evidence_*.jsonl"):
            return f
        return None
        
    def locate_statistics_report(self, strategy_id: str) -> Optional[Path]:
        path = self.base_dir / "docs" / "statistical_validation" / "01_expectancy.md"
        return path if path.exists() else None
        
    def locate_certification_report(self, strategy_id: str) -> Optional[Path]:
        path = self.base_dir / "docs" / "strategy_certification" / f"{strategy_id}_cert.md"
        return path if path.exists() else None
        
    def locate_live_drift_report(self, strategy_id: str) -> Optional[Path]:
        path = self.base_dir / "docs" / "live_drift" / "06_certification_status.md"
        return path if path.exists() else None
