from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.structural_edge_campaign import (
    CampaignAdapterError,
    CampaignContract,
    CampaignContractError,
    CampaignEvidenceError,
    build_ml_v2_development_evidence,
    evaluate_campaign,
)


SPEC_HASH = "a" * 64
CANDIDATE_HASH = "b" * 64
CERT_HASH = "c" * 64
TOKEN_HASH = "d" * 64


def contract(*, hypotheses: int = 1) -> CampaignContract:
    rows = []
    for index in range(hypotheses):
        rows.append(
            {
                "hypothesis_id": f"H{index + 1}",
                "family": "test_family",
                "frozen_spec_sha256": chr(ord("a") + index) * 64,
                "evidence_dir": f"h{index + 1}",
                "max_variants": 2,
            }
        )
    return CampaignContract.from_mapping(
        {
            "schema_version": "1.0",
            "campaign_id": "campaign-test",
            "global_holdout_id": "holdout-v1",
            "max_total_hypotheses": max(1, hypotheses),
            "hypotheses": rows,
            "thresholds": {
                "min_option_trades": 50,
                "min_after_cost_expectancy": 0.05,
                "min_profit_factor": 1.25,
                "max_drawdown": 0.20,
                "min_positive_wfa_partition_fraction": 0.80,
                "expectancy_basis": "net_r_per_trade",
                "drawdown_basis": "fraction_initial_capital",
                "max_contamination_count": 0,
                "max_ambiguity_count": 0,
                "max_fallback_rows": 0,
            },
        }
    )


def write_hashed_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(data)
    path.with_name(path.name + ".sha256").write_text(
        f"{hashlib.sha256(data).hexdigest()}  {path.name}\n",
        encoding="utf-8",
    )


def common(stage: str, hypothesis_id: str = "H1", spec_hash: str = SPEC_HASH) -> dict:
    return {
        "stage": stage,
        "hypothesis_id": hypothesis_id,
        "frozen_spec_sha256": spec_hash,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def write_development(
    root: Path,
    *,
    verdict: str = "CANDIDATE_FROZEN",
    candidate_hash: str | None = CANDIDATE_HASH,
) -> None:
    payload = {
        **common("development"),
        "verdict": verdict,
        "candidate_count": 1 if candidate_hash else 0,
        "candidate_bundle_hash": candidate_hash,
        "validation_v1_consumed_loaded": False,
        "holdout_v1_locked_loaded": False,
        "fresh_confirmation_loaded": False,
    }
    write_hashed_json(root / "h1" / "development.json", payload)


def write_pre_holdout_pass(root: Path) -> None:
    write_development(root)
    write_hashed_json(
        root / "h1" / "fresh_confirmation.json",
        {
            **common("fresh_confirmation"),
            "verdict": "FRESH_CONFIRMATION_PASS",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "fresh_confirmation_consumed_once": True,
            "used_for_tuning": False,
            "holdout_loaded": False,
        },
    )
    write_hashed_json(
        root / "h1" / "causal_replay.json",
        {
            **common("causal_replay"),
            "verdict": "STRUCTURAL_SCREEN_PASS",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "session_clustered": True,
            "multiple_testing_controlled": True,
            "negative_controls_passed": True,
            "parameter_neighborhood_stable": True,
            "future_mutation_oracle_passed": True,
            "holdout_loaded": False,
        },
    )
    write_hashed_json(
        root / "h1" / "option_replay.json",
        {
            **common("option_replay"),
            "verdict": "STRICT_OPTION_REPLAY_PASS",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "strict_mode": True,
            "certifiable": True,
            "holdout_loaded": False,
            "engine_module": "core.option_backtest.engine.OptionBacktestEngine",
            "expectancy_basis": "net_r_per_trade",
            "drawdown_basis": "fraction_initial_capital",
            "trades_taken": 60,
            "after_cost_expectancy": 0.08,
            "profit_factor": 1.40,
            "max_drawdown": 0.15,
            "contamination_count": 0,
            "ambiguity_count": 0,
            "fallback_rows": 0,
        },
    )
    write_hashed_json(
        root / "h1" / "wfa.json",
        {
            **common("wfa"),
            "verdict": "OPTION_WFA_PASS",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "holdout_evaluated": False,
            "train_only_selection": True,
            "frozen_parameters": True,
            "expectancy_basis": "net_r_per_trade",
            "drawdown_basis": "fraction_initial_capital",
            "positive_partition_fraction": 1.0,
            "contamination_count": 0,
        },
    )


def write_selection(root: Path) -> None:
    write_hashed_json(
        root / "global_selection.json",
        {
            "stage": "global_selection",
            "verdict": "GLOBAL_CANDIDATE_SELECTED",
            "hypothesis_id": "H1",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "selection_input_candidate_hashes": [CANDIDATE_HASH],
            "selection_rule_frozen": True,
            "selection_used_holdout": False,
            "holdout_loaded": False,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    )


def write_holdout(root: Path, verdict: str) -> None:
    write_hashed_json(
        root / "global_holdout.json",
        {
            "stage": "global_holdout",
            "verdict": verdict,
            "hypothesis_id": "H1",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "global_holdout_id": "holdout-v1",
            "consumption_count": 1,
            "unlock_token_hash": TOKEN_HASH,
            "used_for_tuning": False,
            "selection_frozen_before_unlock": True,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    )


def test_missing_development_blocks(tmp_path: Path) -> None:
    result = evaluate_campaign(contract(), tmp_path)
    assert result.verdict == "BLOCKED_NO_DEVELOPMENT_EVIDENCE"
    assert result.active_hypothesis_id == "H1"


def test_no_candidate_is_valid_negative_result(tmp_path: Path) -> None:
    write_development(
        tmp_path,
        verdict="NO_STABLE_CANDIDATE",
        candidate_hash=None,
    )
    result = evaluate_campaign(contract(), tmp_path)
    assert result.verdict == "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET"


def test_frozen_candidate_requires_new_confirmation(tmp_path: Path) -> None:
    write_development(tmp_path)
    result = evaluate_campaign(contract(), tmp_path)
    assert result.verdict == "BLOCKED_NEED_NEW_FRESH_CONFIRMATION_DATA"
    assert result.candidate_bundle_hash == CANDIDATE_HASH


def test_fallback_rows_in_option_evidence_fail_closed(tmp_path: Path) -> None:
    write_pre_holdout_pass(tmp_path)
    option_path = tmp_path / "h1" / "option_replay.json"
    payload = json.loads(option_path.read_text())
    payload["fallback_rows"] = 1
    write_hashed_json(option_path, payload)
    with pytest.raises(CampaignEvidenceError, match="fallback rows"):
        evaluate_campaign(contract(), tmp_path)


def test_wfa_survivor_requires_global_selection(tmp_path: Path) -> None:
    write_pre_holdout_pass(tmp_path)
    result = evaluate_campaign(contract(), tmp_path)
    assert result.verdict == "BLOCKED_GLOBAL_SELECTION_REQUIRED"


def test_failed_global_holdout_terminates_campaign(tmp_path: Path) -> None:
    write_pre_holdout_pass(tmp_path)
    write_selection(tmp_path)
    write_holdout(tmp_path, "GLOBAL_LOCKED_HOLDOUT_FAIL")
    result = evaluate_campaign(contract(), tmp_path)
    assert result.verdict == "GLOBAL_HOLDOUT_FAILED_CAMPAIGN_TERMINATED"
    assert result.selected_hypothesis_id == "H1"


def test_full_certification_path(tmp_path: Path) -> None:
    write_pre_holdout_pass(tmp_path)
    write_selection(tmp_path)
    write_holdout(tmp_path, "GLOBAL_LOCKED_HOLDOUT_PASS")
    write_hashed_json(
        tmp_path / "certification.json",
        {
            "stage": "certification",
            "verdict": "IMMUTABLE_CERTIFICATION_PASS",
            "hypothesis_id": "H1",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "source_roles_complete": True,
            "hashes_verified": True,
            "certification_bundle_hash": CERT_HASH,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    )
    write_hashed_json(
        tmp_path / "paper_shadow_implementation.json",
        {
            "stage": "paper_shadow_implementation",
            "verdict": "PAPER_SHADOW_IMPLEMENTATION_PASS",
            "hypothesis_id": "H1",
            "candidate_bundle_hash": CANDIDATE_HASH,
            "paper_only": True,
            "shadow_only": True,
            "enabled_by_default": False,
            "manual_approval_required": True,
            "fallback_executable": False,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    )
    result = evaluate_campaign(contract(), tmp_path)
    assert result.verdict == "ONE_STRUCTURAL_EDGE_CANDIDATE_CERTIFIED"
    assert result.candidate_bundle_hash == CANDIDATE_HASH


def test_candidate_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    write_development(tmp_path)
    write_hashed_json(
        tmp_path / "h1" / "fresh_confirmation.json",
        {
            **common("fresh_confirmation"),
            "verdict": "FRESH_CONFIRMATION_PASS",
            "candidate_bundle_hash": "e" * 64,
            "fresh_confirmation_consumed_once": True,
            "used_for_tuning": False,
            "holdout_loaded": False,
        },
    )
    with pytest.raises(CampaignEvidenceError, match="candidate_bundle_hash"):
        evaluate_campaign(contract(), tmp_path)


def test_search_budget_above_forty_is_rejected() -> None:
    with pytest.raises(CampaignContractError, match="40-variant"):
        CampaignContract.from_mapping(
            {
                "schema_version": "1.0",
                "campaign_id": "bad",
                "global_holdout_id": "holdout",
                "max_total_hypotheses": 1,
                "hypotheses": [
                    {
                        "hypothesis_id": "H1",
                        "family": "bad",
                        "frozen_spec_sha256": SPEC_HASH,
                        "evidence_dir": "h1",
                        "max_variants": 41,
                    }
                ],
                "thresholds": {
                    "min_option_trades": 50,
                    "min_after_cost_expectancy": 0.05,
                    "min_profit_factor": 1.25,
                    "max_drawdown": 0.20,
                    "min_positive_wfa_partition_fraction": 0.80,
                    "expectancy_basis": "net_r_per_trade",
                    "drawdown_basis": "fraction_initial_capital",
                },
            }
        )


def ml_contract() -> CampaignContract:
    return CampaignContract.from_mapping(
        {
            "schema_version": "1.0",
            "campaign_id": "ml-campaign",
            "global_holdout_id": "holdout-v1",
            "max_total_hypotheses": 1,
            "hypotheses": [
                {
                    "hypothesis_id": "ML_V2_LONG",
                    "family": "causal_ml_rule_discovery_long",
                    "frozen_spec_sha256": SPEC_HASH,
                    "evidence_dir": "ml_v2_long",
                    "max_variants": 10,
                }
            ],
            "thresholds": {
                "min_option_trades": 50,
                "min_after_cost_expectancy": 0.05,
                "min_profit_factor": 1.25,
                "max_drawdown": 0.20,
                "min_positive_wfa_partition_fraction": 0.80,
                "expectancy_basis": "net_r_per_trade",
                "drawdown_basis": "fraction_initial_capital",
            },
        }
    )


def write_v2_sources(
    root: Path,
    *,
    candidates: list[dict],
    verdict: str,
    holdout_loaded: bool = False,
) -> tuple[Path, Path]:
    frozen = root / "frozen_candidates.json"
    partition = root / "partition_registry.json"
    frozen.write_text(
        json.dumps(
            {
                "verdict": verdict,
                "candidates": candidates,
                "confirmation_token_issued": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }
        )
    )
    partition.write_text(
        json.dumps(
            {
                "loaded_partition": "DEVELOPMENT_V1",
                "validation_v1_consumed_loaded": False,
                "holdout_v1_locked_loaded": holdout_loaded,
                "fresh_confirmation_loaded": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }
        )
    )
    return frozen, partition


def test_ml_v2_adapter_preserves_no_candidate_verdict(tmp_path: Path) -> None:
    frozen, partition = write_v2_sources(
        tmp_path,
        candidates=[],
        verdict="NO_STABLE_CANDIDATE",
    )
    payload = build_ml_v2_development_evidence(
        contract=ml_contract(),
        hypothesis_id="ML_V2_LONG",
        side="LONG",
        frozen_candidates_path=frozen,
        partition_registry_path=partition,
    )
    assert payload["verdict"] == "NO_STABLE_CANDIDATE"
    assert payload["candidate_count"] == 0
    assert payload["candidate_bundle_hash"] is None


def test_ml_v2_adapter_binds_frozen_candidate_hash(tmp_path: Path) -> None:
    frozen, partition = write_v2_sources(
        tmp_path,
        candidates=[
            {
                "side": "LONG",
                "candidate_bundle_hash": CANDIDATE_HASH,
            }
        ],
        verdict="ONE_LONG_V2_CANDIDATE_FROZEN",
    )
    payload = build_ml_v2_development_evidence(
        contract=ml_contract(),
        hypothesis_id="ML_V2_LONG",
        side="LONG",
        frozen_candidates_path=frozen,
        partition_registry_path=partition,
    )
    assert payload["verdict"] == "CANDIDATE_FROZEN"
    assert payload["candidate_bundle_hash"] == CANDIDATE_HASH


def test_ml_v2_adapter_rejects_holdout_leakage(tmp_path: Path) -> None:
    frozen, partition = write_v2_sources(
        tmp_path,
        candidates=[],
        verdict="NO_STABLE_CANDIDATE",
        holdout_loaded=True,
    )
    with pytest.raises(CampaignAdapterError, match="protected partition"):
        build_ml_v2_development_evidence(
            contract=ml_contract(),
            hypothesis_id="ML_V2_LONG",
            side="LONG",
            frozen_candidates_path=frozen,
            partition_registry_path=partition,
        )
