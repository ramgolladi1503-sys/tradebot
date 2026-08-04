from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class SessionEvidence:
    session_id: str
    verdict: str
    valid: bool
    expiry_session: bool | None
    strategy_diagnosis_ready: bool
    live_shadow_consistent: bool | None
    source_path: str

    @classmethod
    def from_report(cls, path: str | Path) -> "SessionEvidence":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("session_report_not_object")
        manifest = payload.get("manifest")
        readiness = payload.get("outcome_readiness")
        if not isinstance(manifest, Mapping) or not isinstance(readiness, Mapping):
            raise ValueError("session_report_sections_missing")
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
        session_id = str(manifest.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_report_session_id_missing")
        expiry_raw = metadata.get("expiry_session")
        consistency_raw = metadata.get("live_shadow_consistent")
        return cls(session_id, str(manifest.get("verdict") or ""), bool(manifest.get("valid")), bool(expiry_raw) if expiry_raw is not None else None, bool(readiness.get("ready_for_strategy_diagnosis")), bool(consistency_raw) if consistency_raw is not None else None, source.as_posix())


@dataclass(frozen=True)
class CampaignEvidenceSummary:
    total_sessions: int
    valid_sessions: int
    invalid_sessions: int
    expiry_sessions: int
    non_expiry_sessions: int
    unclassified_expiry_sessions: int
    diagnosis_ready_sessions: int
    live_shadow_evaluated_sessions: int
    live_shadow_consistent_sessions: int
    ready_for_multi_session_review: bool
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {"total_sessions": self.total_sessions, "valid_sessions": self.valid_sessions, "invalid_sessions": self.invalid_sessions, "expiry_sessions": self.expiry_sessions, "non_expiry_sessions": self.non_expiry_sessions, "unclassified_expiry_sessions": self.unclassified_expiry_sessions, "diagnosis_ready_sessions": self.diagnosis_ready_sessions, "live_shadow_evaluated_sessions": self.live_shadow_evaluated_sessions, "live_shadow_consistent_sessions": self.live_shadow_consistent_sessions, "ready_for_multi_session_review": self.ready_for_multi_session_review, "blockers": list(self.blockers), "evidence_refs": list(self.evidence_refs)}


def summarize_campaign(sessions: Iterable[SessionEvidence], *, minimum_valid_sessions: int, minimum_expiry_sessions: int, minimum_non_expiry_sessions: int, require_all_diagnosis_ready: bool, require_live_shadow_for_all_valid: bool) -> CampaignEvidenceSummary:
    rows = list(sessions)
    if min(minimum_valid_sessions, minimum_expiry_sessions, minimum_non_expiry_sessions) < 0:
        raise ValueError("campaign_minimum_negative")
    ids = [row.session_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("campaign_duplicate_session_id")
    valid = [row for row in rows if row.valid]
    expiry = [row for row in valid if row.expiry_session is True]
    non_expiry = [row for row in valid if row.expiry_session is False]
    unclassified = [row for row in valid if row.expiry_session is None]
    diagnosis_ready = [row for row in valid if row.strategy_diagnosis_ready]
    live_shadow_evaluated = [row for row in valid if row.live_shadow_consistent is not None]
    live_shadow_consistent = [row for row in valid if row.live_shadow_consistent is True]
    blockers: list[str] = []
    if len(valid) < minimum_valid_sessions: blockers.append("INSUFFICIENT_VALID_SESSIONS")
    if len(expiry) < minimum_expiry_sessions: blockers.append("INSUFFICIENT_EXPIRY_SESSIONS")
    if len(non_expiry) < minimum_non_expiry_sessions: blockers.append("INSUFFICIENT_NON_EXPIRY_SESSIONS")
    if require_all_diagnosis_ready and len(diagnosis_ready) != len(valid): blockers.append("SESSION_DIAGNOSIS_INCOMPLETE")
    if require_live_shadow_for_all_valid:
        if len(live_shadow_evaluated) != len(valid): blockers.append("LIVE_SHADOW_NOT_EVALUATED_FOR_ALL_VALID_SESSIONS")
        elif len(live_shadow_consistent) != len(valid): blockers.append("LIVE_SHADOW_DIVERGENCE")
    return CampaignEvidenceSummary(len(rows), len(valid), len(rows) - len(valid), len(expiry), len(non_expiry), len(unclassified), len(diagnosis_ready), len(live_shadow_evaluated), len(live_shadow_consistent), not blockers, tuple(blockers), tuple(sorted(row.source_path for row in rows)))
