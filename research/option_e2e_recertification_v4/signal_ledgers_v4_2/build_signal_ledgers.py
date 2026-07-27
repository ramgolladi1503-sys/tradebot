from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


HISTORICAL_RESEARCH_HYPOTHESES = (
    "Residual Mean Reversion",
    "Opening-State Momentum",
    "Constituent Lead-Lag weighted",
    "Constituent Breadth unweighted",
    "RSI2 research",
    "ML-discovered campaigns",
)


@dataclass(frozen=True)
class SignalLedgerRecord:
    strategy_or_hypothesis_id: str
    signal_id: str
    session: str
    feature_cutoff_ts: str
    signal_ts: str
    earliest_entry_ts: str
    direction: str
    signal_strength: str
    params_hash: str
    source_hash: str
    implementation_sha: str
    fold_id: str
    is_holdout: bool
    status: str
    blocker: str


def build_signal_ledgers(inventory_path: Path) -> tuple[list[SignalLedgerRecord], dict[str, Any]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    strategy_ids = [entry["id"] for entry in inventory["entities"] if entry.get("counted_as_strategy")]
    records = [SignalLedgerRecord(
        strategy_or_hypothesis_id=strategy_id,
        signal_id=f"{strategy_id}:signal_blocked",
        session="frozen",
        feature_cutoff_ts="",
        signal_ts="",
        earliest_entry_ts="",
        direction="NA",
        signal_strength="0",
        params_hash="",
        source_hash="",
        implementation_sha="",
        fold_id="",
        is_holdout=False,
        status="SIGNAL_INPUT_DATA_MISSING",
        blocker="NO_SIGNAL_LEDGER_SOURCE",
    ) for strategy_id in strategy_ids]
    records.extend(
        SignalLedgerRecord(
            strategy_or_hypothesis_id=hypothesis,
            signal_id=f"{hypothesis}:hypothesis_blocked",
            session="frozen",
            feature_cutoff_ts="",
            signal_ts="",
            earliest_entry_ts="",
            direction="NA",
            signal_strength="0",
            params_hash="",
            source_hash="",
            implementation_sha="",
            fold_id="",
            is_holdout=False,
            status="SIGNAL_INPUT_DATA_MISSING",
            blocker="NO_SIGNAL_LEDGER_SOURCE",
        )
        for hypothesis in HISTORICAL_RESEARCH_HYPOTHESES
    )
    summary = {
        "strategy_count": len(strategy_ids),
        "hypothesis_count": len(HISTORICAL_RESEARCH_HYPOTHESES),
        "status_counts": {"SIGNAL_INPUT_DATA_MISSING": len(records)},
        "blocked_eligibility": len(records),
    }
    return records, summary


def write_signal_ledgers(records: list[SignalLedgerRecord], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "records": [asdict(record) for record in records]}
    (output_dir / "signal_ledgers.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "signal_ledgers_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256((output_dir / "signal_ledgers.json").read_bytes()).hexdigest()
    (output_dir / "signal_ledgers.json.sha256").write_text(f"{digest}  signal_ledgers.json\n", encoding="utf-8")

