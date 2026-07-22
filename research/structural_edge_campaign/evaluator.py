from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .contracts import CampaignContract, HypothesisContract


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CampaignEvidenceError(ValueError):
    """Raised when campaign evidence violates the frozen campaign contract."""


@dataclass(frozen=True)
class CampaignEvaluation:
    verdict: str
    campaign_id: str
    active_hypothesis_id: str | None
    candidate_bundle_hash: str | None
    selected_hypothesis_id: str | None
    trace: tuple[dict[str, Any], ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "campaign_id": self.campaign_id,
            "verdict": self.verdict,
            "active_hypothesis_id": self.active_hypothesis_id,
            "selected_hypothesis_id": self.selected_hypothesis_id,
            "candidate_bundle_hash": self.candidate_bundle_hash,
            "trace": list(self.trace),
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value.lower()))


def _load(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise CampaignEvidenceError(f"evidence path is not a file: {path}")
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.is_file():
        raise CampaignEvidenceError(f"missing SHA-256 sidecar: {sidecar}")
    data = path.read_bytes()
    tokens = sidecar.read_text(encoding="utf-8").strip().split()
    if not tokens or not _valid_hash(tokens[0]):
        raise CampaignEvidenceError(f"invalid SHA-256 sidecar: {sidecar}")
    if hashlib.sha256(data).hexdigest() != tokens[0].lower():
        raise CampaignEvidenceError(f"SHA-256 mismatch: {path}")
    payload = json.loads(data)
    if not isinstance(payload, Mapping):
        raise CampaignEvidenceError(f"evidence must be a JSON object: {path}")
    return payload


def _expect(payload: Mapping[str, Any], **expected: Any) -> None:
    stage = payload.get("stage", "unknown")
    for field, value in expected.items():
        if payload.get(field) != value:
            raise CampaignEvidenceError(
                f"{stage}:{field} expected {value!r}, got {payload.get(field)!r}"
            )


def _safety(payload: Mapping[str, Any], *, read_only: bool = True) -> None:
    if read_only:
        _expect(payload, read_only=True)
    _expect(
        payload,
        is_order_action=False,
        broker_api_called=False,
        allowed_for_live_execution=False,
    )


def _stage(
    payload: Mapping[str, Any],
    hypothesis: HypothesisContract,
    name: str,
    candidate_hash: str | None = None,
) -> None:
    _expect(
        payload,
        stage=name,
        hypothesis_id=hypothesis.hypothesis_id,
        frozen_spec_sha256=hypothesis.frozen_spec_sha256,
    )
    _safety(payload)
    if candidate_hash is not None:
        _expect(payload, candidate_bundle_hash=candidate_hash)


def _number(payload: Mapping[str, Any], field: str) -> float:
    try:
        return float(payload[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignEvidenceError(f"{payload.get('stage')}:{field} is invalid") from exc


def _integer(payload: Mapping[str, Any], field: str) -> int:
    if isinstance(payload.get(field), bool):
        raise CampaignEvidenceError(f"{payload.get('stage')}:{field} is invalid")
    try:
        return int(payload[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignEvidenceError(f"{payload.get('stage')}:{field} is invalid") from exc


def _row(hypothesis_id: str | None, stage: str, verdict: str) -> dict[str, Any]:
    return {"hypothesis_id": hypothesis_id, "stage": stage, "verdict": verdict}


def _result(
    contract: CampaignContract,
    trace: list[dict[str, Any]],
    verdict: str,
    *,
    active: str | None = None,
    candidate_hash: str | None = None,
    selected: str | None = None,
) -> CampaignEvaluation:
    return CampaignEvaluation(
        verdict=verdict,
        campaign_id=contract.campaign_id,
        active_hypothesis_id=active,
        candidate_bundle_hash=candidate_hash,
        selected_hypothesis_id=selected,
        trace=tuple(trace),
    )


def _artifact(root: Path, hypothesis: HypothesisContract, name: str):
    directory = (root / hypothesis.evidence_dir).resolve()
    if root != directory and root not in directory.parents:
        raise CampaignEvidenceError("hypothesis evidence directory escapes root")
    return _load(directory / f"{name}.json")


def evaluate_campaign(
    contract: CampaignContract,
    evidence_root: str | Path,
) -> CampaignEvaluation:
    root = Path(evidence_root).expanduser().resolve()
    trace: list[dict[str, Any]] = []
    contenders: dict[str, HypothesisContract] = {}

    for hypothesis in contract.hypotheses:
        dev = _artifact(root, hypothesis, "development")
        if dev is None:
            trace.append(_row(hypothesis.hypothesis_id, "development", "MISSING"))
            return _result(
                contract,
                trace,
                "BLOCKED_NO_DEVELOPMENT_EVIDENCE",
                active=hypothesis.hypothesis_id,
            )
        _stage(dev, hypothesis, "development")
        for field in (
            "validation_v1_consumed_loaded",
            "holdout_v1_locked_loaded",
            "fresh_confirmation_loaded",
        ):
            _expect(dev, **{field: False})
        verdict = str(dev.get("verdict", ""))
        count = _integer(dev, "candidate_count")
        candidate_hash = dev.get("candidate_bundle_hash")
        trace.append(_row(hypothesis.hypothesis_id, "development", verdict))
        if verdict == "NO_STABLE_CANDIDATE":
            if count != 0 or candidate_hash is not None:
                raise CampaignEvidenceError("no-candidate verdict carries a candidate")
            continue
        if verdict != "CANDIDATE_FROZEN" or count != 1 or not _valid_hash(candidate_hash):
            raise CampaignEvidenceError("invalid frozen development candidate")
        candidate_hash = str(candidate_hash).lower()

        confirm = _artifact(root, hypothesis, "fresh_confirmation")
        if confirm is None:
            trace.append(_row(hypothesis.hypothesis_id, "fresh_confirmation", "MISSING"))
            return _result(
                contract,
                trace,
                "BLOCKED_NEED_NEW_FRESH_CONFIRMATION_DATA",
                active=hypothesis.hypothesis_id,
                candidate_hash=candidate_hash,
            )
        _stage(confirm, hypothesis, "fresh_confirmation", candidate_hash)
        _expect(
            confirm,
            fresh_confirmation_consumed_once=True,
            used_for_tuning=False,
            holdout_loaded=False,
        )
        verdict = str(confirm.get("verdict", ""))
        trace.append(_row(hypothesis.hypothesis_id, "fresh_confirmation", verdict))
        if verdict == "FRESH_CONFIRMATION_FAIL":
            continue
        if verdict != "FRESH_CONFIRMATION_PASS":
            raise CampaignEvidenceError("unsupported fresh-confirmation verdict")

        causal = _artifact(root, hypothesis, "causal_replay")
        if causal is None:
            trace.append(_row(hypothesis.hypothesis_id, "causal_replay", "MISSING"))
            return _result(
                contract,
                trace,
                "BLOCKED_NEED_CAUSAL_REPLAY",
                active=hypothesis.hypothesis_id,
                candidate_hash=candidate_hash,
            )
        _stage(causal, hypothesis, "causal_replay", candidate_hash)
        verdict = str(causal.get("verdict", ""))
        trace.append(_row(hypothesis.hypothesis_id, "causal_replay", verdict))
        if verdict == "STRUCTURAL_SCREEN_FAIL":
            continue
        if verdict != "STRUCTURAL_SCREEN_PASS":
            raise CampaignEvidenceError("unsupported causal-replay verdict")
        _expect(
            causal,
            session_clustered=True,
            multiple_testing_controlled=True,
            negative_controls_passed=True,
            parameter_neighborhood_stable=True,
            future_mutation_oracle_passed=True,
            holdout_loaded=False,
        )

        option = _artifact(root, hypothesis, "option_replay")
        if option is None:
            trace.append(_row(hypothesis.hypothesis_id, "option_replay", "MISSING"))
            return _result(
                contract,
                trace,
                "BLOCKED_NEED_STRICT_OPTION_REPLAY",
                active=hypothesis.hypothesis_id,
                candidate_hash=candidate_hash,
            )
        _stage(option, hypothesis, "option_replay", candidate_hash)
        verdict = str(option.get("verdict", ""))
        trace.append(_row(hypothesis.hypothesis_id, "option_replay", verdict))
        if verdict == "STRICT_OPTION_REPLAY_FAIL":
            continue
        if verdict != "STRICT_OPTION_REPLAY_PASS":
            raise CampaignEvidenceError("unsupported option-replay verdict")
        _expect(
            option,
            strict_mode=True,
            certifiable=True,
            holdout_loaded=False,
            engine_module="core.option_backtest.engine.OptionBacktestEngine",
            expectancy_basis=contract.thresholds.expectancy_basis,
            drawdown_basis=contract.thresholds.drawdown_basis,
        )
        gates = (
            (_integer(option, "trades_taken") >= contract.thresholds.min_option_trades, "trade-count"),
            (_number(option, "after_cost_expectancy") > contract.thresholds.min_after_cost_expectancy, "expectancy"),
            (_number(option, "profit_factor") >= contract.thresholds.min_profit_factor, "profit-factor"),
            (_number(option, "max_drawdown") <= contract.thresholds.max_drawdown, "drawdown"),
            (_integer(option, "contamination_count") <= contract.thresholds.max_contamination_count, "contamination"),
            (_integer(option, "ambiguity_count") <= contract.thresholds.max_ambiguity_count, "ambiguity"),
            (_integer(option, "fallback_rows") <= contract.thresholds.max_fallback_rows, "fallback rows"),
        )
        failed = next((name for passed, name in gates if not passed), None)
        if failed:
            raise CampaignEvidenceError(
                f"{hypothesis.hypothesis_id}: option {failed} gate not met"
            )

        wfa = _artifact(root, hypothesis, "wfa")
        if wfa is None:
            trace.append(_row(hypothesis.hypothesis_id, "wfa", "MISSING"))
            return _result(
                contract,
                trace,
                "BLOCKED_NEED_OPTION_WFA",
                active=hypothesis.hypothesis_id,
                candidate_hash=candidate_hash,
            )
        _stage(wfa, hypothesis, "wfa", candidate_hash)
        _expect(
            wfa,
            holdout_evaluated=False,
            train_only_selection=True,
            frozen_parameters=True,
            expectancy_basis=contract.thresholds.expectancy_basis,
            drawdown_basis=contract.thresholds.drawdown_basis,
        )
        verdict = str(wfa.get("verdict", ""))
        trace.append(_row(hypothesis.hypothesis_id, "wfa", verdict))
        if verdict == "OPTION_WFA_FAIL":
            continue
        if verdict != "OPTION_WFA_PASS":
            raise CampaignEvidenceError("unsupported WFA verdict")
        if (
            _number(wfa, "positive_partition_fraction")
            < contract.thresholds.min_positive_wfa_partition_fraction
            or _integer(wfa, "contamination_count") != 0
        ):
            raise CampaignEvidenceError("WFA stability or contamination gate not met")
        contenders[candidate_hash] = hypothesis

    if not contenders:
        return _result(
            contract, trace, "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET"
        )

    selection = _load(root / "global_selection.json")
    if selection is None:
        trace.append(_row(None, "global_selection", "MISSING"))
        return _result(contract, trace, "BLOCKED_GLOBAL_SELECTION_REQUIRED")
    _expect(
        selection,
        stage="global_selection",
        verdict="GLOBAL_CANDIDATE_SELECTED",
        holdout_loaded=False,
        selection_used_holdout=False,
        selection_rule_frozen=True,
    )
    _safety(selection)
    inputs = selection.get("selection_input_candidate_hashes")
    if not isinstance(inputs, list) or set(inputs) != set(contenders):
        raise CampaignEvidenceError("global selection input set mismatch")
    selected_hash = selection.get("candidate_bundle_hash")
    if selected_hash not in contenders:
        raise CampaignEvidenceError("global selection chose a non-contender")
    selected_hypothesis = contenders[str(selected_hash)]
    _expect(selection, hypothesis_id=selected_hypothesis.hypothesis_id)
    trace.append(_row(selected_hypothesis.hypothesis_id, "global_selection", "GLOBAL_CANDIDATE_SELECTED"))

    holdout = _load(root / "global_holdout.json")
    if holdout is None:
        trace.append(_row(selected_hypothesis.hypothesis_id, "global_holdout", "MISSING"))
        return _result(
            contract,
            trace,
            "BLOCKED_GLOBAL_HOLDOUT_NOT_RUN",
            active=selected_hypothesis.hypothesis_id,
            candidate_hash=str(selected_hash),
            selected=selected_hypothesis.hypothesis_id,
        )
    _expect(
        holdout,
        stage="global_holdout",
        hypothesis_id=selected_hypothesis.hypothesis_id,
        candidate_bundle_hash=selected_hash,
        global_holdout_id=contract.global_holdout_id,
        consumption_count=1,
        used_for_tuning=False,
        selection_frozen_before_unlock=True,
    )
    _safety(holdout)
    if not _valid_hash(holdout.get("unlock_token_hash")):
        raise CampaignEvidenceError("invalid global holdout unlock token hash")
    verdict = str(holdout.get("verdict", ""))
    trace.append(_row(selected_hypothesis.hypothesis_id, "global_holdout", verdict))
    if verdict == "GLOBAL_LOCKED_HOLDOUT_FAIL":
        return _result(
            contract,
            trace,
            "GLOBAL_HOLDOUT_FAILED_CAMPAIGN_TERMINATED",
            candidate_hash=str(selected_hash),
            selected=selected_hypothesis.hypothesis_id,
        )
    if verdict != "GLOBAL_LOCKED_HOLDOUT_PASS":
        raise CampaignEvidenceError("unsupported global holdout verdict")

    cert = _load(root / "certification.json")
    if cert is None:
        trace.append(_row(selected_hypothesis.hypothesis_id, "certification", "MISSING"))
        return _result(
            contract,
            trace,
            "BLOCKED_IMMUTABLE_CERTIFICATION_REQUIRED",
            active=selected_hypothesis.hypothesis_id,
            candidate_hash=str(selected_hash),
            selected=selected_hypothesis.hypothesis_id,
        )
    _expect(
        cert,
        stage="certification",
        verdict="IMMUTABLE_CERTIFICATION_PASS",
        hypothesis_id=selected_hypothesis.hypothesis_id,
        candidate_bundle_hash=selected_hash,
        source_roles_complete=True,
        hashes_verified=True,
    )
    _safety(cert)
    if not _valid_hash(cert.get("certification_bundle_hash")):
        raise CampaignEvidenceError("invalid certification bundle hash")
    trace.append(_row(selected_hypothesis.hypothesis_id, "certification", "IMMUTABLE_CERTIFICATION_PASS"))

    implementation = _load(root / "paper_shadow_implementation.json")
    if implementation is None:
        trace.append(_row(selected_hypothesis.hypothesis_id, "paper_shadow_implementation", "MISSING"))
        return _result(
            contract,
            trace,
            "BLOCKED_PAPER_SHADOW_IMPLEMENTATION_REQUIRED",
            active=selected_hypothesis.hypothesis_id,
            candidate_hash=str(selected_hash),
            selected=selected_hypothesis.hypothesis_id,
        )
    _expect(
        implementation,
        stage="paper_shadow_implementation",
        verdict="PAPER_SHADOW_IMPLEMENTATION_PASS",
        hypothesis_id=selected_hypothesis.hypothesis_id,
        candidate_bundle_hash=selected_hash,
        paper_only=True,
        shadow_only=True,
        enabled_by_default=False,
        manual_approval_required=True,
        fallback_executable=False,
    )
    _safety(implementation, read_only=False)
    trace.append(_row(selected_hypothesis.hypothesis_id, "paper_shadow_implementation", "PAPER_SHADOW_IMPLEMENTATION_PASS"))
    return _result(
        contract,
        trace,
        "ONE_STRUCTURAL_EDGE_CANDIDATE_CERTIFIED",
        candidate_hash=str(selected_hash),
        selected=selected_hypothesis.hypothesis_id,
    )
