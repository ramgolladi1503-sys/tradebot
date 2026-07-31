"""Append-only JSONL recorder for the unified campaign."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Mapping

from core.unified_live_validation_pr748_756.campaign_contract import CampaignIdentity, enrich_row


class AppendOnlyRecorder:
    """Small append-only writer with per-row safety fields."""

    def __init__(self, identity: CampaignIdentity):
        self.identity = identity
        self.root = Path(identity.evidence_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, relative_path: str, row: Mapping[str, Any], *, pr_number: int) -> Path:
        if relative_path.startswith("/") or ".." in Path(relative_path).parts:
            raise ValueError("relative_path_must_stay_inside_evidence_root")
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = enrich_row(self.identity, row, pr_number=pr_number)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))
            handle.write("\n")
        return path

