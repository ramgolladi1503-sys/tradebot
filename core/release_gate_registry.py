"""Repository-owned release gate generator registry and verification contracts.

Binds semantic gate names to immutable generator identities, execution
contracts, measured observation schemas, and recomputation predicates.
Prevents caller-authored PASS and generic exit-code-zero placeholders.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

EVALUATOR_VERSION_V2 = "release_gate_registry_v2"
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class GateContract:
    gate: str
    generator_id: str
    generator_version: str
    command_prefix: str
    required_observed_keys: frozenset[str]
    offline_safe: bool = True
    broker_write_required: bool = False
    live_market_required: bool = False


# All 18 gates required by UNKNOWN_IMPACT under release change impact analysis
GATE_REGISTRY: dict[str, GateContract] = {
    "source_identity": GateContract(
        gate="source_identity",
        generator_id="tradebot:source_identity_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="git cat-file -e",
        required_observed_keys=frozenset({"commit_exists", "head_sha"}),
    ),
    "whole_tree_compile": GateContract(
        gate="whole_tree_compile",
        generator_id="tradebot:whole_tree_compile_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="python3 -m compileall",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "compiled_modules_count"}),
    ),
    "diff_check": GateContract(
        gate="diff_check",
        generator_id="tradebot:diff_check_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="git diff --check",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "whitespace_clean"}),
    ),
    "release_verifier": GateContract(
        gate="release_verifier",
        generator_id="tradebot:release_verifier_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_release_certification.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "verifier_pass"}),
    ),
    "decision_tests": GateContract(
        gate="decision_tests",
        generator_id="tradebot:decision_tests_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_read_only_consumer_cycle.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "tests_passed"}),
    ),
    "decision_isolation": GateContract(
        gate="decision_isolation",
        generator_id="tradebot:decision_isolation_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_sqlite_runtime_isolation.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "isolation_verified"}),
    ),
    "degraded_mode": GateContract(
        gate="degraded_mode",
        generator_id="tradebot:degraded_mode_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_depth_persistence_batching.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "degraded_mode_verified"}),
    ),
    "decision_mutations": GateContract(
        gate="decision_mutations",
        generator_id="tradebot:decision_mutations_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_depth_persistence_batching.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "mutations_detected"}),
    ),
    "persistence": GateContract(
        gate="persistence",
        generator_id="tradebot:persistence_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_depth_persistence_batching.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "persistence_verified"}),
    ),
    "critical_mutations": GateContract(
        gate="critical_mutations",
        generator_id="tradebot:critical_mutations_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="python3 scripts/release_manager_mutation_campaign.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "mandatory_mutations_detected", "total_mutations"}),
    ),
    "cas_memory": GateContract(
        gate="cas_memory",
        generator_id="tradebot:cas_memory_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_market_session_memory_sidecar.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "memory_sidecar_verified"}),
    ),
    "morning_readiness": GateContract(
        gate="morning_readiness",
        generator_id="tradebot:morning_readiness_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_morning_readiness_v1.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "readiness_state_machine_verified"}),
    ),
    "instrument_authority": GateContract(
        gate="instrument_authority",
        generator_id="tradebot:instrument_authority_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_daily_instrument_authority.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "authority_derivation_verified"}),
    ),
    "feed_subscription": GateContract(
        gate="feed_subscription",
        generator_id="tradebot:feed_subscription_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_depth_subscription_refresh_contract.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "subscription_contract_verified"}),
    ),
    "shutdown_seal": GateContract(
        gate="shutdown_seal",
        generator_id="tradebot:shutdown_seal_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="pytest tests/test_morning_shutdown_and_mutations.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "shutdown_seals_verified"}),
    ),
    "option_mirror": GateContract(
        gate="option_mirror",
        generator_id="tradebot:option_mirror_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="python3 scripts/generate_option_mirror_primitive.py",
        required_observed_keys=frozenset({"command", "exit_code", "raw_stdout_sha256", "offline_readiness_transition_valid", "degraded_fallback_verified"}),
    ),
    "evidence_integrity": GateContract(
        gate="evidence_integrity",
        generator_id="tradebot:evidence_integrity_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="python3 scripts/generate_evidence_integrity_primitive.py",
        required_observed_keys=frozenset({
            "command", "exit_code", "raw_stdout_sha256", "manifest_present",
            "manifest_schema_valid", "artifact_paths_safe", "artifacts_exist",
            "artifact_hashes_verified", "bundle_digest",
        }),
    ),
    "security_authority": GateContract(
        gate="security_authority",
        generator_id="tradebot:security_authority_v2",
        generator_version=EVALUATOR_VERSION_V2,
        command_prefix="python3 scripts/generate_security_authority_primitive.py",
        required_observed_keys=frozenset({
            "command", "exit_code", "raw_stdout_sha256",
            "singular_candidate_selection_authority_verified",
            "singular_execution_authority_verified",
            "observer_execution_isolation_verified",
            "broker_write_calls_measured", "order_actions_measured",
            "measurement_method",
        }),
    ),
}


def is_generic_exit_code_zero_placeholder(observed: Mapping[str, Any]) -> bool:
    """Detect unauthoritative generic placeholder primitives like {"command": "governed:<gate>", "exit_code": 0}."""
    if not isinstance(observed, dict):
        return True
    cmd = observed.get("command")
    keys = set(observed.keys())
    if keys == {"command", "exit_code"} and isinstance(cmd, str) and cmd.startswith("governed:"):
        return True
    if "raw_stdout_sha256" not in observed and observed.get("exit_code") == 0:
        return True
    return False


def validate_gate_predicate_v2(gate: str, observed: Mapping[str, Any], repo: Path, candidate: str) -> bool:
    """Evaluate candidate evidence against the registered gate contract."""
    contract = GATE_REGISTRY.get(gate)
    if contract is None:
        return False
    if not isinstance(observed, dict):
        return False

    # Immediate rejection of generic placeholder primitives
    if is_generic_exit_code_zero_placeholder(observed) and gate != "source_identity":
        return False

    # Check required keys
    for key in contract.required_observed_keys:
        if key not in observed:
            return False

    # Gate-specific semantic evaluations
    if gate == "source_identity":
        return observed.get("commit_exists") is True and observed.get("head_sha") == candidate

    exit_code = observed.get("exit_code")
    raw_hash = str(observed.get("raw_stdout_sha256", ""))
    if exit_code != 0 or not SHA256_HEX_RE.fullmatch(raw_hash):
        return False

    cmd = str(observed.get("command", ""))
    if not cmd.startswith(contract.command_prefix):
        return False

    if gate == "whole_tree_compile":
        return int(observed.get("compiled_modules_count", 0)) > 0

    if gate == "diff_check":
        return observed.get("whitespace_clean") is True

    if gate == "release_verifier":
        return observed.get("verifier_pass") is True

    if gate == "decision_tests":
        return int(observed.get("tests_passed", 0)) > 0

    if gate == "decision_isolation":
        return observed.get("isolation_verified") is True

    if gate == "degraded_mode":
        return observed.get("degraded_mode_verified") is True

    if gate == "decision_mutations":
        return int(observed.get("mutations_detected", 0)) > 0

    if gate == "persistence":
        return observed.get("persistence_verified") is True

    if gate == "critical_mutations":
        total = int(observed.get("total_mutations", 0))
        detected = int(observed.get("mandatory_mutations_detected", 0))
        return total >= 15 and detected == total

    if gate == "cas_memory":
        return observed.get("memory_sidecar_verified") is True

    if gate == "morning_readiness":
        return observed.get("readiness_state_machine_verified") is True

    if gate == "instrument_authority":
        return observed.get("authority_derivation_verified") is True

    if gate == "feed_subscription":
        return observed.get("subscription_contract_verified") is True

    if gate == "shutdown_seal":
        return observed.get("shutdown_seals_verified") is True

    if gate == "option_mirror":
        return (
            observed.get("offline_readiness_transition_valid") is True
            and observed.get("degraded_fallback_verified") is True
        )

    if gate == "evidence_integrity":
        return (
            observed.get("manifest_present") is True
            and observed.get("manifest_schema_valid") is True
            and observed.get("artifact_paths_safe") is True
            and observed.get("artifacts_exist") is True
            and observed.get("artifact_hashes_verified") is True
            and SHA256_HEX_RE.fullmatch(str(observed.get("bundle_digest", ""))) is not None
        )

    if gate == "security_authority":
        method = observed.get("measurement_method")
        # Forgery attack rejection: must be measured via spy, not hardcoded constant
        if method != "spy_counter_verified":
            return False
        return (
            observed.get("singular_candidate_selection_authority_verified") is True
            and observed.get("singular_execution_authority_verified") is True
            and observed.get("observer_execution_isolation_verified") is True
            and observed.get("broker_write_calls_measured") == 0
            and observed.get("order_actions_measured") == 0
        )

    return False
