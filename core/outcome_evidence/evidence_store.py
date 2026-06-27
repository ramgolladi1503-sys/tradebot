import json
import dataclasses
from pathlib import Path
from typing import List, Dict, Any
from .evidence_models import OutcomeEvidenceRecord


class OutcomeEvidenceStore:
    """Stores outcome evidence to JSONL."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def _encode_enum(self, obj: Any) -> Any:
        if hasattr(obj, "value"):
            return obj.value
        return obj

    def _dataclass_to_dict(self, obj: Any) -> Dict[str, Any]:
        if not dataclasses.is_dataclass(obj):
            return obj
            
        result: Dict[str, Any] = {}
        for field in dataclasses.fields(obj):
            value = getattr(obj, field.name)
            if dataclasses.is_dataclass(value):
                result[field.name] = self._dataclass_to_dict(value)
            elif isinstance(value, list):
                result[field.name] = [self._dataclass_to_dict(v) if dataclasses.is_dataclass(v) else self._encode_enum(v) for v in value]
            elif value is not None:
                result[field.name] = self._encode_enum(value)
        return result

    def save_records(self, records: List[OutcomeEvidenceRecord], filename: str = "outcome_evidence.jsonl"):
        out_path = self.output_dir / filename
        
        with out_path.open("a", encoding="utf-8") as f:
            for record in records:
                data = self._dataclass_to_dict(record)
                f.write(json.dumps(data) + "\n")
