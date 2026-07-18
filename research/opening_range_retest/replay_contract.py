from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.strategy_parameter_profiles import get_default_profile
from strategies.movement import opening_range_breakout


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_PATH = PROJECT_ROOT / "strategies" / "movement" / "opening_range_breakout.py"
CONTRACT_BUNDLE_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v1.json"
DATASET_MANIFEST_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "four_strategy_dataset_manifest_v3.json"


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


@dataclass(frozen=True)
class ReplayContractMatrix:
    strategy_id: str
    movement_type: str
    temporal_contract_version: str
    strategy_version: str
    opening_range_bar_count: int
    breakout_definition: dict[str, str]
    equality_behavior: str
    wick_only_behavior: str
    retest_definition: dict[str, str]
    breakout_to_retest_max_age: int
    retest_to_continuation_max_age: int
    continuation_definition: dict[str, str]
    invalidation_behavior: dict[str, str]
    session_boundary_behavior: str
    call_direction_behavior: str
    put_direction_behavior: str
    proposal_ready_timestamp_rule: str
    setup_id_inputs: tuple[str, ...]
    history_hash_inputs: tuple[str, ...]
    candidate_fingerprint_fields: tuple[str, ...]
    required_profile_parameters: tuple[str, ...]
    malformed_history_behavior: str
    duplicate_bar_behavior: str
    missing_bar_behavior: str
    permitted_source_symbols: tuple[str, ...]
    source_data_claim_boundary: str
    production_callable: str
    production_module: str
    production_file_sha256: str
    runtime_profile_hash: str
    contract_bundle_sha256: str
    dataset_manifest_sha256: str
    contract_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_replay_contract_matrix() -> ReplayContractMatrix:
    profile = get_default_profile("opening_range_breakout_v1")
    params = tuple(sorted(opening_range_breakout.REQUIRED_PROFILE_KEYS))
    payload = {
        "strategy_id": opening_range_breakout.STRATEGY_ID,
        "movement_type": opening_range_breakout.MOVEMENT_TYPE,
        "temporal_contract_version": opening_range_breakout.TEMPORAL_CONTRACT_VERSION,
        "strategy_version": "v1",
        "opening_range_bar_count": opening_range_breakout.OPENING_RANGE_BARS,
        "breakout_definition": {
            "BUY_CALL": "close > orb_high",
            "BUY_PUT": "close < orb_low",
        },
        "equality_behavior": "close exactly equal to orb_high/orb_low is not a breakout and does not invalidate a pending future setup on its own",
        "wick_only_behavior": "wick beyond ORB without required close is not a breakout",
        "retest_definition": {
            "BUY_CALL": "low <= orb_high and close >= orb_high and low > orb_low",
            "BUY_PUT": "high >= orb_low and close <= orb_low and high < orb_high",
        },
        "breakout_to_retest_max_age": opening_range_breakout.MAX_BREAKOUT_TO_RETEST_AGE,
        "retest_to_continuation_max_age": opening_range_breakout.MAX_RETEST_TO_CONTINUATION_AGE,
        "continuation_definition": {
            "BUY_CALL": "close > retest_bar.high",
            "BUY_PUT": "close < retest_bar.low",
        },
        "invalidation_behavior": {
            "BUY_CALL": "close < orb_high resets the pending setup",
            "BUY_PUT": "close > orb_low resets the pending setup",
        },
        "session_boundary_behavior": "single IST cash-session only; exact contiguous one-minute bars from 09:15 are required; later-session continuation is rejected",
        "call_direction_behavior": "CALL lane scans ORB_HIGH breakout, retest hold, then continuation",
        "put_direction_behavior": "PUT lane scans ORB_LOW breakout, retest hold, then continuation",
        "proposal_ready_timestamp_rule": "proposal_ready_at_iso equals the continuation bar end timestamp when the continuation bar is the latest completed bar in the causal prefix",
        "setup_id_inputs": (
            "strategy_id",
            "symbol",
            "session_date",
            "direction",
            "boundary_type",
            "normalized_boundary_value",
            "breakout_timestamp",
        ),
        "history_hash_inputs": (
            "bar_start_timestamp",
            "open",
            "high",
            "low",
            "close",
        ),
        "candidate_fingerprint_fields": (
            "strategy_id",
            "direction",
            "status",
            "raw_score",
            "entry_trigger",
            "invalid_if",
            "rank_reason",
            "setup_id",
            "history_hash",
            "proposal_ready_at_iso",
        ),
        "required_profile_parameters": params,
        "malformed_history_behavior": "fail closed",
        "duplicate_bar_behavior": "fail closed via duplicate start timestamp rejection",
        "missing_bar_behavior": "fail closed via exact one-minute cadence enforcement",
        "permitted_source_symbols": ("NIFTY", "BANKNIFTY", "SENSEX"),
        "source_data_claim_boundary": "Phase 1 validates signal-generation causality only on approved underlying candle corpus with proxy VWAP allowed where exact truth is unavailable; no execution, profitability, or live-readiness claim",
        "production_callable": "strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates",
        "production_module": "strategies.movement.opening_range_breakout",
        "production_file_sha256": sha256_file(STRATEGY_PATH),
        "runtime_profile_hash": str(profile.parameter_hash),
        "contract_bundle_sha256": sha256_file(CONTRACT_BUNDLE_PATH),
        "dataset_manifest_sha256": sha256_file(DATASET_MANIFEST_PATH),
    }
    contract_hash = sha256_bytes(canonical_json_bytes(payload))
    return ReplayContractMatrix(contract_hash=contract_hash, **payload)
