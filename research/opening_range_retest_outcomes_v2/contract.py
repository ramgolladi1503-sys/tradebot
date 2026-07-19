from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "opening_range_retest_outcome_contract_v2"
HORIZONS_MINUTES = (1, 3, 5, 15, 30)
INPUT_SOURCE_HASH = "243efbbda2dfbe90817408e50a54c5377f45dbb86db460918edb334fc57d3039"
INPUT_CANDIDATE_CORE_HASH = "8f28637e86095884b76ff931bf4f8b1606301895a226f7839949152c630e189a"
INPUT_CANDIDATE_PROVENANCE_HASH = "b198ebab71cdc4b097360fb2280f2da6ac2ad1595c0da917dbd5a0b7a2dbba48"
INPUT_SOURCE_COUNT = 1512
INPUT_CANDIDATE_COUNT = 2215
EVIDENCE_TIMESTAMP = "2026-07-19T00:00:00Z"


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safety_fields() -> dict[str, bool]:
    return {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def evidence_fields(*, mode: str, decision: str, reason: str, source: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "candidate_id": "ALL_ORB_PHASE1_V2_CANDIDATES",
        "decision": decision,
        "reason": reason,
        "timestamp": EVIDENCE_TIMESTAMP,
        "source": source,
    }


def build_contract(*, source_authority_root: str, base_main_sha: str, execution_commit_sha: str) -> dict[str, Any]:
    contract = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        **evidence_fields(
            mode="ORB_OUTCOME_CONTRACT_V2",
            decision="ORB_OUTCOME_CONTRACT_V2_FROZEN",
            reason="strict offline underlying-outcome contract frozen after PR 676 merge",
            source="opening_range_retest_causal_replay_summary_v2.json",
        ),
        "base_main_sha": base_main_sha,
        "execution_commit_sha": execution_commit_sha,
        "inputs": {
            "source_count": INPUT_SOURCE_COUNT,
            "source_semantic_hash": INPUT_SOURCE_HASH,
            "candidate_count": INPUT_CANDIDATE_COUNT,
            "candidate_core_semantic_hash": INPUT_CANDIDATE_CORE_HASH,
            "candidate_provenance_semantic_hash": INPUT_CANDIDATE_PROVENANCE_HASH,
        },
        "source_authority": {
            "root": source_authority_root,
            "logical_prefix": "runtime/upstox_candidate_replay",
            "mutate": False,
            "copy": False,
            "symlink": False,
        },
        "bars": {
            "label": "start-labelled 1-minute bars",
            "session_timezone": "Asia/Kolkata",
            "session_start": "09:15",
            "session_last_start": "15:29",
            "cadence_seconds": 60,
        },
        "entry": {
            "primary_rule": "first bar whose start is strictly greater than proposal_ready_at_iso",
            "price": "legal entry bar open",
            "same_timestamp_bar_disposition": "SKIPPED_FOR_PRIMARY",
        },
        "horizons_minutes": list(HORIZONS_MINUTES),
        "horizon_terminal_rule": {
            "1": "close of entry bar",
            "3": "close of bar starting entry+2m",
            "5": "close of bar starting entry+4m",
            "15": "close of bar starting entry+14m",
            "30": "close of bar starting entry+29m",
            "selection": "exact timestamps only",
        },
        "returns": {
            "BUY_CALL": "(terminal_close - entry_open) / entry_open",
            "BUY_PUT": "(entry_open - terminal_close) / entry_open",
            "unsigned": "(terminal_close - entry_open) / entry_open",
        },
        "mfe_mae": {
            "interval": "entry through terminal inclusive",
            "BUY_CALL_MFE": "(max_high - entry_open) / entry_open",
            "BUY_CALL_MAE": "(min_low - entry_open) / entry_open",
            "BUY_PUT_MFE": "(entry_open - min_low) / entry_open",
            "BUY_PUT_MAE": "(entry_open - max_high) / entry_open",
            "mae_signed": True,
        },
        "overlap": {"interval": "[legal_entry_start, terminal_bar_end)", "canonical": "reported_not_removed"},
        "claim_boundary": [
            "DESCRIPTIVE_ONLY",
            "PRE_COST_UNDERLYING_ONLY",
            "NOT_EDGE_EVIDENCE",
            "NOT_OPTION_PNL",
            "NOT_PROFITABILITY",
            "NOT_PAPER_OR_LIVE_READY",
        ],
        **safety_fields(),
    }
    contract["contract_hash"] = sha256_bytes(canonical_json_bytes({k: v for k, v in contract.items() if k != "contract_hash"}))
    return contract
