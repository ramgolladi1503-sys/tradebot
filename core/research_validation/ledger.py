from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


_UNKNOWN = {"", "unknown", "unidentified", "none", "null", "n/a"}


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    hypothesis_id: str
    strategy_id: str
    code_sha: str
    data_snapshot_sha256: str
    parameters: Mapping[str, Any]
    status: str
    selected: bool
    metrics: Mapping[str, Any]
    parent_trial_id: str | None = None


def _required_text(name: str, value: str) -> str:
    text = str(value).strip()
    if text.lower() in _UNKNOWN:
        raise ValueError(f"trial_{name}_missing")
    return text


def validate_trial_ledger(records: Iterable[TrialRecord]) -> tuple[TrialRecord, ...]:
    rows = tuple(records)
    if not rows:
        raise ValueError("trial_ledger_empty")
    ids: set[str] = set()
    for row in rows:
        trial_id = _required_text("id", row.trial_id)
        if trial_id in ids:
            raise ValueError("trial_id_duplicate")
        ids.add(trial_id)
        _required_text("hypothesis_id", row.hypothesis_id)
        _required_text("strategy_id", row.strategy_id)
        _required_text("code_sha", row.code_sha)
        _required_text("data_snapshot_sha256", row.data_snapshot_sha256)
        _required_text("status", row.status)
        if not isinstance(row.parameters, Mapping):
            raise ValueError("trial_parameters_must_be_mapping")
        if not isinstance(row.metrics, Mapping):
            raise ValueError("trial_metrics_must_be_mapping")
    for row in rows:
        if row.parent_trial_id is not None and row.parent_trial_id not in ids:
            raise ValueError("trial_parent_not_in_ledger")
    return rows


def trial_ledger_sha256(records: Iterable[TrialRecord]) -> str:
    rows = validate_trial_ledger(records)
    payload = [asdict(row) for row in sorted(rows, key=lambda item: item.trial_id)]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def summarize_trial_ledger(records: Iterable[TrialRecord]) -> dict[str, Any]:
    rows = validate_trial_ledger(records)
    selected = [row for row in rows if row.selected]
    hypotheses = {row.hypothesis_id for row in rows}
    strategies = {row.strategy_id for row in rows}
    return {
        "total_trials": len(rows),
        "selected_trials": len(selected),
        "hypotheses_tested": len(hypotheses),
        "strategy_ids_tested": len(strategies),
        "ledger_sha256": trial_ledger_sha256(rows),
        "search_history_complete": True,
    }
