import json
from typing import Iterator
from pathlib import Path

from .evidence_types import CandidateSourceStatus, EvidenceQuality
from .evidence_models import ReplayCandidate


class CandidateLoader:
    """Loads strategy candidates from historical telemetry (JSONL or SQLite)."""

    def __init__(self, source_path: Path):
        self.source_path = Path(source_path)

    def load_jsonl(self) -> Iterator[ReplayCandidate]:
        """Load candidates from a candidate_decisions.jsonl or decision_events.jsonl file."""
        if not self.source_path.exists():
            return

        with self.source_path.open("r", encoding="utf-8") as f:
            for offset, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                yield self._parse_json_line(line, offset)

    def _parse_json_line(self, line: str, offset: int) -> ReplayCandidate:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return ReplayCandidate(
                candidate_id=None,
                strategy_id=None,
                timestamp=0.0,
                instrument_id=None,
                underlying=None,
                entry_price=None,
                stop_price=None,
                target_price=None,
                source_path=str(self.source_path),
                source_offset=offset,
                source_status=CandidateSourceStatus.UNPARSABLE,
                evidence_quality=EvidenceQuality.UNUSABLE
            )

        candidate_id = str(data.get("candidate_id") or data.get("decision_id")) if data.get("candidate_id") or data.get("decision_id") else None
        strategy_id = str(data.get("strategy_id")) if data.get("strategy_id") else None
        strategy_version = data.get("strategy_version")
        timestamp = float(data.get("timestamp") or data.get("timestamp_epoch", 0.0))
        instrument_id = str(data.get("instrument_id") or data.get("option_symbol")) if data.get("instrument_id") or data.get("option_symbol") else None
        underlying = str(data.get("underlying") or data.get("index_name")) if data.get("underlying") or data.get("index_name") else None
        
        # Prices
        entry_price = float(data.get("entry_price") or data.get("entry")) if data.get("entry_price") or data.get("entry") else None
        stop_price = float(data.get("stop_price") or data.get("stop")) if data.get("stop_price") or data.get("stop") else None
        target_price = float(data.get("target_price") or data.get("target")) if data.get("target_price") or data.get("target") else None
        time_stop = data.get("time_stop")
        if time_stop is not None:
            time_stop = float(time_stop)

        option_symbol = data.get("option_symbol")
        strike = data.get("strike")
        if strike is not None:
            strike = float(strike)
        option_type = data.get("option_type")
        
        # Execution eligibility
        execution_ok = bool(data.get("execution_ok", False))
        if "veto_reasons" not in data and not execution_ok and data.get("status") == "EXECUTED":
            execution_ok = True
            
        blockers = data.get("veto_reasons") or data.get("blockers") or []
        rejection_reasons = data.get("pilot_reasons") or data.get("rejection_reasons") or []
        ranking_bucket = data.get("ranking_bucket") or data.get("score_bucket")

        # Determine evidence quality
        missing_fields = []
        if not candidate_id:
            missing_fields.append("candidate_id")
        if entry_price is None:
            missing_fields.append("entry_price")
        if stop_price is None:
            missing_fields.append("stop_price")
        if target_price is None:
            missing_fields.append("target_price")
            
        quality = EvidenceQuality.COMPLETE
        status = CandidateSourceStatus.LOADED
        if missing_fields:
            status = CandidateSourceStatus.MISSING_FIELDS
            quality = EvidenceQuality.UNUSABLE

        return ReplayCandidate(
            candidate_id=candidate_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            timestamp=timestamp,
            instrument_id=instrument_id,
            underlying=underlying,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            option_symbol=option_symbol,
            strike=strike,
            expiry=data.get("expiry"),
            option_type=option_type,
            time_stop=time_stop,
            execution_ok=execution_ok,
            blockers=blockers,
            rejection_reasons=rejection_reasons,
            ranking_bucket=ranking_bucket,
            source_path=str(self.source_path),
            source_offset=offset,
            source_status=status,
            evidence_quality=quality
        )
