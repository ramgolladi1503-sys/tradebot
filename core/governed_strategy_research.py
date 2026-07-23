"""Fail-closed control plane for agent-assisted strategy research.

This module coordinates research evidence. It never calls a broker, changes live
configuration, or grants live execution authority. Codex and Antigravity remain
engineering/review agents; deterministic code and a human remain the authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
ALLOWED_AGENTS = frozenset({"codex", "antigravity", "manual"})
MANDATORY_GATES = (
    "causal_timestamps",
    "next_bar_execution",
    "transaction_costs",
    "deterministic_replay",
    "negative_controls",
    "walk_forward_analysis",
    "untouched_holdout",
    "independent_oracle",
    "artifact_integrity",
)
FORBIDDEN_PATH_PREFIXES = (
    ".env",
    "config/credentials",
    "credentials.py",
    "core/broker",
    "core/execution",
    "core/order",
    "core/risk",
    "core/feed",
    "main.py",
    "run_live.sh",
    "runtime/live",
    "secrets",
)
SAFETY_ASSERTIONS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "live_mode_touched": False,
    "allowed_for_runtime_wiring": False,
    "allowed_for_live_execution": False,
}


class ResearchError(RuntimeError):
    """Raised when a fail-closed research gate rejects an operation."""


class ResearchState(str, Enum):
    INTAKE = "INTAKE"
    HYPOTHESIS_FROZEN = "HYPOTHESIS_FROZEN"
    IMPLEMENTED = "IMPLEMENTED"
    AUDITED = "AUDITED"
    VALIDATED = "VALIDATED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REVIEW_REWRITE = "REVIEW_REWRITE"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"


class AgentRole(str, Enum):
    EXPLORER = "EXPLORER"
    IMPLEMENTER = "IMPLEMENTER"
    AUDITOR = "AUDITOR"


_REQUIRED_HYPOTHESIS_FIELDS = (
    "thesis",
    "market",
    "timeframe",
    "data_universe",
    "development_window",
    "holdout_window",
    "signal_definition",
    "entry_rule",
    "exit_rule",
    "cost_model",
    "negative_controls",
    "primary_metric",
    "rejection_criteria",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - parser message varies by Python
        raise ResearchError(
            f"{label}_unreadable:{type(exc).__name__}:{exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ResearchError(f"{label}_must_be_object")
    return dict(payload)


def _safe_relative_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ResearchError(f"unsafe_relative_path:{text or 'missing'}")
    return path.as_posix()


def _verified_artifact_json(
    root: Path,
    relative_path: object,
    expected_file_sha256: object,
    *,
    label: str,
) -> tuple[str, dict[str, Any]]:
    relative = _safe_relative_path(relative_path)
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise ResearchError(f"{label}_not_found")
    expected = str(expected_file_sha256 or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ResearchError(f"{label}_file_sha256_required")
    if _sha256_file(path) != expected:
        raise ResearchError(f"{label}_file_hash_mismatch")
    return relative, _load_json_object(path, label=label)


def _normalize_agent(agent: object) -> str:
    value = (
        str(agent or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )
    if value not in ALLOWED_AGENTS:
        raise ResearchError(f"unknown_agent:{value or 'missing'}")
    return value


def _path_is_forbidden(path: str) -> bool:
    normalized = path.casefold().rstrip("/")
    return any(
        normalized.startswith(prefix.casefold().rstrip("/"))
        for prefix in FORBIDDEN_PATH_PREFIXES
    )


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value)
    return value is not None


def _validate_hypothesis(payload: Mapping[str, Any]) -> tuple[str, ...]:
    blockers = [
        f"missing_hypothesis_field:{field}"
        for field in _REQUIRED_HYPOTHESIS_FIELDS
        if not _nonempty(payload.get(field))
    ]
    controls = payload.get("negative_controls")
    if (
        isinstance(controls, Sequence)
        and not isinstance(controls, (str, bytes))
        and len(controls) < 2
    ):
        blockers.append("at_least_two_negative_controls_required")
    if payload.get("outcomes_observed") not in (None, False):
        blockers.append("hypothesis_must_be_frozen_before_outcomes")
    if payload.get("tunable_after_freeze") not in (None, False):
        blockers.append("post_freeze_tuning_forbidden")
    return tuple(sorted(set(blockers)))


def _event(
    previous_hash: str | None,
    event_type: str,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "created_at": _utc_now(),
        "event_type": event_type,
        "previous_event_sha256": previous_hash,
        "details": dict(details),
    }
    payload["event_sha256"] = _sha256_payload(payload)
    return payload


@dataclass(frozen=True)
class ResearchStatus:
    run_id: str
    strategy_id: str
    state: str
    hypothesis_sha256: str | None
    implementation_sha256: str | None
    review_sha256: str | None
    validation_sha256: str | None
    allowed_for_paper: bool
    allowed_for_live_execution: bool
    integrity_ok: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "state": self.state,
            "hypothesis_sha256": self.hypothesis_sha256,
            "implementation_sha256": self.implementation_sha256,
            "review_sha256": self.review_sha256,
            "validation_sha256": self.validation_sha256,
            "allowed_for_paper": self.allowed_for_paper,
            "allowed_for_live_execution": self.allowed_for_live_execution,
            "integrity_ok": self.integrity_ok,
            "blockers": list(self.blockers),
        }


class GovernedResearchStore:
    """Persistent state machine for one governed strategy-research run."""

    def __init__(self, run_dir: str | Path):
        self.root = Path(run_dir).expanduser().resolve()
        self.manifest_path = self.root / "manifest.json"
        self.hypothesis_path = self.root / "hypothesis_frozen.json"
        self.evidence_dir = self.root / "evidence"
        self.packet_dir = self.root / "agent_packets"

    @classmethod
    def initialize(
        cls,
        run_dir: str | Path,
        *,
        strategy_id: str,
        title: str,
        objective: str,
        implementer: str = "codex",
        reviewer: str = "antigravity",
    ) -> "GovernedResearchStore":
        store = cls(run_dir)
        if store.manifest_path.exists():
            raise ResearchError("run_already_initialized")
        implementer = _normalize_agent(implementer)
        reviewer = _normalize_agent(reviewer)
        if implementer == reviewer:
            raise ResearchError("reviewer_must_be_independent")
        strategy_id = str(strategy_id or "").strip()
        title = str(title or "").strip()
        objective = str(objective or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{2,100}", strategy_id):
            raise ResearchError("invalid_strategy_id")
        if not title or not objective:
            raise ResearchError("title_and_objective_required")
        run_id = hashlib.sha256(
            f"{strategy_id}|{title}|{objective}".encode("utf-8")
        ).hexdigest()[:24]
        first_event = _event(None, "RUN_INITIALIZED", {"strategy_id": strategy_id})
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "strategy_id": strategy_id,
            "title": title,
            "objective": objective,
            "state": ResearchState.INTAKE.value,
            "implementer": implementer,
            "reviewer": reviewer,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "hypothesis_sha256": None,
            "implementation_sha256": None,
            "review_sha256": None,
            "validation_sha256": None,
            "allowed_for_paper": False,
            "approved_by": None,
            "safety": dict(SAFETY_ASSERTIONS),
            "events": [first_event],
        }
        manifest["manifest_sha256"] = _sha256_payload(
            {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        )
        _atomic_write_json(store.manifest_path, manifest)
        return store

    def _manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            raise ResearchError("run_not_initialized")
        return _load_json_object(self.manifest_path, label="manifest")

    def _save_manifest(
        self,
        manifest: dict[str, Any],
        event_type: str,
        details: Mapping[str, Any],
    ) -> None:
        events = list(manifest.get("events") or [])
        previous = events[-1].get("event_sha256") if events else None
        events.append(_event(str(previous) if previous else None, event_type, details))
        manifest["events"] = events
        manifest["updated_at"] = _utc_now()
        manifest["manifest_sha256"] = _sha256_payload(
            {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        )
        _atomic_write_json(self.manifest_path, manifest)

    def freeze_hypothesis(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        manifest = self._manifest()
        if manifest["state"] not in {
            ResearchState.INTAKE.value,
            ResearchState.REVIEW_REWRITE.value,
        }:
            raise ResearchError(f"cannot_freeze_from_state:{manifest['state']}")
        blockers = _validate_hypothesis(payload)
        if blockers:
            raise ResearchError(";".join(blockers))
        frozen = dict(payload)
        frozen.update(
            {
                "schema_version": SCHEMA_VERSION,
                "strategy_id": manifest["strategy_id"],
                "run_id": manifest["run_id"],
                "frozen_at": _utc_now(),
                "outcomes_observed": False,
                "tunable_after_freeze": False,
            }
        )
        frozen["contract_sha256"] = _sha256_payload(frozen)
        _atomic_write_json(self.hypothesis_path, frozen)
        manifest["state"] = ResearchState.HYPOTHESIS_FROZEN.value
        manifest["hypothesis_sha256"] = frozen["contract_sha256"]
        manifest["implementation_sha256"] = None
        manifest["review_sha256"] = None
        manifest["validation_sha256"] = None
        manifest["allowed_for_paper"] = False
        self._save_manifest(
            manifest,
            "HYPOTHESIS_FROZEN",
            {"contract_sha256": frozen["contract_sha256"]},
        )
        return frozen

    def build_agent_packet(self, *, agent: str, role: str | AgentRole) -> Path:
        manifest = self._manifest()
        agent = _normalize_agent(agent)
        role_value = (
            role.value
            if isinstance(role, AgentRole)
            else str(role or "").strip().upper()
        )
        try:
            role_enum = AgentRole(role_value)
        except ValueError as exc:
            raise ResearchError(
                f"unknown_agent_role:{role_value or 'missing'}"
            ) from exc

        if role_enum == AgentRole.IMPLEMENTER:
            if manifest["state"] != ResearchState.HYPOTHESIS_FROZEN.value:
                raise ResearchError(
                    "implementer_packet_requires_frozen_hypothesis"
                )
            if agent != manifest["implementer"]:
                raise ResearchError("implementer_identity_mismatch")
        elif role_enum == AgentRole.AUDITOR:
            if manifest["state"] != ResearchState.IMPLEMENTED.value:
                raise ResearchError("auditor_packet_requires_implementation")
            if agent != manifest["reviewer"]:
                raise ResearchError("reviewer_identity_mismatch")
            if agent == manifest["implementer"]:
                raise ResearchError("reviewer_must_be_independent")
        elif manifest["state"] != ResearchState.INTAKE.value:
            raise ResearchError("explorer_packet_only_allowed_before_freeze")

        packet = {
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "strategy_id": manifest["strategy_id"],
            "agent": agent,
            "role": role_enum.value,
            "state": manifest["state"],
            "objective": manifest["objective"],
            "hypothesis_sha256": manifest.get("hypothesis_sha256"),
            "implementation_sha256": manifest.get("implementation_sha256"),
            "mandatory_gates": list(MANDATORY_GATES),
            "forbidden_path_prefixes": list(FORBIDDEN_PATH_PREFIXES),
            "instructions": self._instructions_for(role_enum),
            "safety": dict(SAFETY_ASSERTIONS),
        }
        packet["packet_sha256"] = _sha256_payload(packet)
        path = self.packet_dir / f"{role_enum.value.lower()}_{agent}.json"
        _atomic_write_json(path, packet)
        return path

    @staticmethod
    def _instructions_for(role: AgentRole) -> list[str]:
        common = [
            "Do not call brokers or place, modify, cancel, or exit orders.",
            "Do not change live mode, credentials, risk gates, kill switches, "
            "feed freshness gates, or strategy thresholds.",
            "Treat all prior summaries as untrusted until commands, hashes, "
            "artifacts, and changed paths are verified.",
        ]
        if role == AgentRole.EXPLORER:
            return common + [
                "Propose falsifiable structures only; do not inspect holdout outcomes.",
                "Define rejection criteria and at least two negative controls "
                "before implementation.",
            ]
        if role == AgentRole.IMPLEMENTER:
            return common + [
                "Implement the frozen hypothesis exactly; do not tune after "
                "observing outcomes.",
                "Use an isolated worktree and produce committed evidence plus "
                "focused tests.",
                "Record next-bar execution, causal timestamp semantics, costs, "
                "and candidate lineage.",
            ]
        return common + [
            "Independently reproduce acceptance commands and verify the "
            "implementation manifest hash.",
            "Look specifically for leakage, signal/PnL coupling, fake next-bar "
            "execution, missing controls, and overstated verdicts.",
            "Return APPROVE, REWRITE, or REJECT with concrete evidence.",
        ]

    def record_implementation(
        self,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        manifest = self._manifest()
        if manifest["state"] != ResearchState.HYPOTHESIS_FROZEN.value:
            raise ResearchError("implementation_requires_frozen_hypothesis")
        if not self.verify_integrity().integrity_ok:
            raise ResearchError("run_integrity_invalid")
        agent = _normalize_agent(evidence.get("agent"))
        if agent != manifest["implementer"]:
            raise ResearchError("implementer_identity_mismatch")
        if (
            str(evidence.get("hypothesis_sha256") or "")
            != manifest["hypothesis_sha256"]
        ):
            raise ResearchError("implementation_hypothesis_hash_mismatch")
        base_commit = str(evidence.get("base_commit") or "").strip()
        head_commit = str(evidence.get("head_commit") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base_commit) or not re.fullmatch(
            r"[0-9a-f]{40}", head_commit
        ):
            raise ResearchError("implementation_commit_sha_required")
        if base_commit == head_commit:
            raise ResearchError("implementation_must_change_committed_head")
        changed_paths_raw = evidence.get("changed_paths")
        if (
            not isinstance(changed_paths_raw, Sequence)
            or isinstance(changed_paths_raw, (str, bytes))
            or not changed_paths_raw
        ):
            raise ResearchError("implementation_changed_paths_required")
        changed_paths = [_safe_relative_path(path) for path in changed_paths_raw]
        forbidden = [path for path in changed_paths if _path_is_forbidden(path)]
        if forbidden:
            raise ResearchError(
                "forbidden_implementation_paths:"
                + ",".join(sorted(forbidden))
            )
        supervisor_path, supervisor_manifest = _verified_artifact_json(
            self.root,
            evidence.get("supervisor_manifest"),
            evidence.get("supervisor_manifest_file_sha256"),
            label="supervisor_manifest",
        )
        if str(supervisor_manifest.get("state") or "").upper() != "VERIFIED":
            raise ResearchError("supervisor_manifest_not_verified")
        if str(supervisor_manifest.get("base_commit") or "") != base_commit:
            raise ResearchError("supervisor_manifest_base_commit_mismatch")
        if str(supervisor_manifest.get("head_commit") or "") != head_commit:
            raise ResearchError("supervisor_manifest_head_commit_mismatch")
        supervisor_paths = sorted(
            set(str(path) for path in supervisor_manifest.get("changed_paths") or [])
        )
        if supervisor_paths != sorted(set(changed_paths)):
            raise ResearchError("supervisor_manifest_changed_paths_mismatch")
        supervisor_safety = supervisor_manifest.get("safety")
        if not isinstance(supervisor_safety, Mapping):
            raise ResearchError("supervisor_manifest_safety_missing")
        if (
            supervisor_safety.get("broker_api_called") is not False
            or supervisor_safety.get("allowed_for_live_execution") is not False
        ):
            raise ResearchError("supervisor_manifest_safety_invalid")
        supervisor_internal_hash = str(
            supervisor_manifest.get("manifest_sha256") or ""
        ).strip()
        if not re.fullmatch(r"[0-9a-f]{64}", supervisor_internal_hash):
            raise ResearchError("supervisor_manifest_internal_hash_missing")
        test_results = evidence.get("test_results")
        if (
            not isinstance(test_results, Sequence)
            or isinstance(test_results, (str, bytes))
            or not test_results
        ):
            raise ResearchError("implementation_test_results_required")
        normalized_tests: list[dict[str, Any]] = []
        for result in test_results:
            if not isinstance(result, Mapping):
                raise ResearchError("implementation_test_result_invalid")
            name = str(result.get("name") or "").strip()
            if not name or result.get("exit_code") != 0:
                raise ResearchError("implementation_tests_must_pass")
            normalized_tests.append(
                {
                    "name": name,
                    "exit_code": 0,
                    "command": list(result.get("command") or []),
                }
            )
        normalized = {
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "agent": agent,
            "hypothesis_sha256": manifest["hypothesis_sha256"],
            "base_commit": base_commit,
            "head_commit": head_commit,
            "branch": str(evidence.get("branch") or "").strip(),
            "changed_paths": sorted(set(changed_paths)),
            "test_results": normalized_tests,
            "artifacts": list(evidence.get("artifacts") or []),
            "supervisor_manifest": supervisor_path,
            "supervisor_manifest_file_sha256": str(
                evidence.get("supervisor_manifest_file_sha256")
            ),
            "supervisor_manifest_sha256": supervisor_internal_hash,
            "supervisor_task_id": str(supervisor_manifest.get("task_id") or ""),
            "recorded_at": _utc_now(),
            "safety": dict(SAFETY_ASSERTIONS),
        }
        normalized["implementation_sha256"] = _sha256_payload(normalized)
        _atomic_write_json(self.evidence_dir / "implementation.json", normalized)
        manifest["state"] = ResearchState.IMPLEMENTED.value
        manifest["implementation_sha256"] = normalized["implementation_sha256"]
        self._save_manifest(
            manifest,
            "IMPLEMENTATION_RECORDED",
            {"implementation_sha256": normalized["implementation_sha256"]},
        )
        return normalized

    def record_review(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        manifest = self._manifest()
        if manifest["state"] != ResearchState.IMPLEMENTED.value:
            raise ResearchError("review_requires_implementation")
        agent = _normalize_agent(evidence.get("agent"))
        if agent != manifest["reviewer"]:
            raise ResearchError("reviewer_identity_mismatch")
        if agent == manifest["implementer"]:
            raise ResearchError("reviewer_must_be_independent")
        if (
            str(evidence.get("implementation_sha256") or "")
            != manifest["implementation_sha256"]
        ):
            raise ResearchError("review_implementation_hash_mismatch")
        implementation_record = _load_json_object(
            self.evidence_dir / "implementation.json",
            label="implementation",
        )
        supervisor_review_path, supervisor_review = _verified_artifact_json(
            self.root,
            evidence.get("supervisor_review_manifest"),
            evidence.get("supervisor_review_manifest_file_sha256"),
            label="supervisor_review_manifest",
        )
        decision = str(evidence.get("decision") or "").strip().upper()
        if decision not in {"APPROVE", "REWRITE", "REJECT"}:
            raise ResearchError("review_decision_invalid")
        if str(supervisor_review.get("reviewer") or "") != agent:
            raise ResearchError("supervisor_review_reviewer_mismatch")
        if (
            str(supervisor_review.get("implementer") or "")
            != manifest["implementer"]
        ):
            raise ResearchError("supervisor_review_implementer_mismatch")
        if str(supervisor_review.get("decision") or "").upper() != decision:
            raise ResearchError("supervisor_review_decision_mismatch")
        if str(
            supervisor_review.get("implementation_manifest_sha256") or ""
        ) != str(implementation_record.get("supervisor_manifest_sha256") or ""):
            raise ResearchError("supervisor_review_implementation_hash_mismatch")
        summary = str(evidence.get("summary") or "").strip()
        if not summary:
            raise ResearchError("review_summary_required")
        reproduction = evidence.get("reproduction_results")
        if (
            not isinstance(reproduction, Sequence)
            or isinstance(reproduction, (str, bytes))
            or not reproduction
        ):
            raise ResearchError("independent_reproduction_required")
        reproduced: list[dict[str, Any]] = []
        for item in reproduction:
            if not isinstance(item, Mapping) or item.get("exit_code") != 0:
                raise ResearchError("review_reproduction_must_pass")
            reproduced.append(
                {"name": str(item.get("name") or "").strip(), "exit_code": 0}
            )
        normalized = {
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "agent": agent,
            "decision": decision,
            "summary": summary,
            "findings": list(evidence.get("findings") or []),
            "required_changes": list(evidence.get("required_changes") or []),
            "implementation_sha256": manifest["implementation_sha256"],
            "reproduction_results": reproduced,
            "supervisor_review_manifest": supervisor_review_path,
            "supervisor_review_manifest_file_sha256": str(
                evidence.get("supervisor_review_manifest_file_sha256")
            ),
            "supervisor_review_manifest_sha256": str(
                supervisor_review.get("manifest_sha256") or ""
            ),
            "recorded_at": _utc_now(),
            "safety": dict(SAFETY_ASSERTIONS),
        }
        normalized["review_sha256"] = _sha256_payload(normalized)
        _atomic_write_json(self.evidence_dir / "review.json", normalized)
        manifest["review_sha256"] = normalized["review_sha256"]
        if decision == "APPROVE":
            manifest["state"] = ResearchState.AUDITED.value
        elif decision == "REWRITE":
            manifest["state"] = ResearchState.REVIEW_REWRITE.value
            manifest["implementation_sha256"] = None
            manifest["review_sha256"] = None
        else:
            manifest["state"] = ResearchState.REVIEW_REJECTED.value
        self._save_manifest(
            manifest,
            f"REVIEW_{decision}",
            {"review_sha256": normalized["review_sha256"]},
        )
        return normalized

    def record_validation(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        manifest = self._manifest()
        if manifest["state"] not in {
            ResearchState.AUDITED.value,
            ResearchState.VALIDATION_FAILED.value,
        }:
            raise ResearchError("validation_requires_approved_audit")
        for field in (
            "hypothesis_sha256",
            "implementation_sha256",
            "review_sha256",
        ):
            if str(evidence.get(field) or "") != str(manifest.get(field) or ""):
                raise ResearchError(f"validation_{field}_mismatch")
        gates = evidence.get("gates")
        if not isinstance(gates, Mapping):
            raise ResearchError("validation_gates_required")
        gate_results: dict[str, Any] = {}
        blockers: list[str] = []
        for gate in MANDATORY_GATES:
            result = gates.get(gate)
            if not isinstance(result, Mapping):
                blockers.append(f"gate_missing:{gate}")
                continue
            passed = result.get("passed") is True
            artifact = str(result.get("artifact") or "").strip()
            artifact_sha256 = str(result.get("artifact_sha256") or "").strip()
            if not passed:
                blockers.append(f"gate_failed:{gate}")
            if not artifact or not artifact_sha256:
                blockers.append(f"gate_artifact_missing:{gate}")
            else:
                artifact_path = (self.root / _safe_relative_path(artifact)).resolve()
                if self.root not in artifact_path.parents:
                    blockers.append(f"gate_artifact_escaped:{gate}")
                elif not artifact_path.is_file():
                    blockers.append(f"gate_artifact_not_found:{gate}")
                elif _sha256_file(artifact_path) != artifact_sha256:
                    blockers.append(f"gate_artifact_hash_mismatch:{gate}")
            details = result.get("details")
            gate_results[gate] = {
                "passed": passed,
                "artifact": artifact,
                "artifact_sha256": artifact_sha256,
                "details": dict(details) if isinstance(details, Mapping) else {},
            }
        normalized = {
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "hypothesis_sha256": manifest["hypothesis_sha256"],
            "implementation_sha256": manifest["implementation_sha256"],
            "review_sha256": manifest["review_sha256"],
            "gates": gate_results,
            "blockers": sorted(set(blockers)),
            "recorded_at": _utc_now(),
            "safety": dict(SAFETY_ASSERTIONS),
        }
        normalized["validation_sha256"] = _sha256_payload(normalized)
        _atomic_write_json(self.evidence_dir / "validation.json", normalized)
        manifest["validation_sha256"] = normalized["validation_sha256"]
        manifest["allowed_for_paper"] = False
        manifest["state"] = (
            ResearchState.VALIDATED.value
            if not blockers
            else ResearchState.VALIDATION_FAILED.value
        )
        self._save_manifest(
            manifest,
            "VALIDATION_COMPLETED",
            {"passed": not blockers, "blockers": sorted(set(blockers))},
        )
        return normalized

    def approve_paper(self, *, approved_by: str) -> ResearchStatus:
        manifest = self._manifest()
        if manifest["state"] != ResearchState.VALIDATED.value:
            raise ResearchError("paper_approval_requires_validated_research")
        approver = str(approved_by or "").strip()
        if not approver:
            raise ResearchError("human_approver_required")
        manifest["state"] = ResearchState.PAPER_ELIGIBLE.value
        manifest["allowed_for_paper"] = True
        manifest["approved_by"] = approver
        self._save_manifest(manifest, "PAPER_APPROVED", {"approved_by": approver})
        return self.status()

    def verify_integrity(self) -> ResearchStatus:
        blockers: list[str] = []
        manifest = self._manifest()
        expected_manifest_hash = _sha256_payload(
            {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        )
        if manifest.get("manifest_sha256") != expected_manifest_hash:
            blockers.append("manifest_hash_invalid")
        previous: str | None = None
        for index, event in enumerate(manifest.get("events") or []):
            if not isinstance(event, Mapping):
                blockers.append(f"event_invalid:{index}")
                continue
            if event.get("previous_event_sha256") != previous:
                blockers.append(f"event_chain_broken:{index}")
            event_copy = dict(event)
            claimed = event_copy.pop("event_sha256", None)
            if claimed != _sha256_payload(event_copy):
                blockers.append(f"event_hash_invalid:{index}")
            previous = str(claimed) if claimed else None
        hypothesis_hash = manifest.get("hypothesis_sha256")
        if hypothesis_hash:
            if not self.hypothesis_path.exists():
                blockers.append("frozen_hypothesis_missing")
            else:
                hypothesis = _load_json_object(
                    self.hypothesis_path,
                    label="hypothesis",
                )
                claimed = hypothesis.pop("contract_sha256", None)
                if claimed != _sha256_payload(hypothesis) or claimed != hypothesis_hash:
                    blockers.append("frozen_hypothesis_hash_invalid")
        for field, filename, hash_field in (
            ("implementation_sha256", "implementation.json", "implementation_sha256"),
            ("review_sha256", "review.json", "review_sha256"),
            ("validation_sha256", "validation.json", "validation_sha256"),
        ):
            claimed_manifest = manifest.get(field)
            if not claimed_manifest:
                continue
            path = self.evidence_dir / filename
            if not path.exists():
                blockers.append(f"{filename}_missing")
                continue
            payload = _load_json_object(path, label=filename)
            claimed_file = payload.pop(hash_field, None)
            if (
                claimed_file != _sha256_payload(payload)
                or claimed_file != claimed_manifest
            ):
                blockers.append(f"{filename}_hash_invalid")
        if manifest.get("safety") != SAFETY_ASSERTIONS:
            blockers.append("safety_assertions_changed")
        return ResearchStatus(
            run_id=str(manifest.get("run_id") or ""),
            strategy_id=str(manifest.get("strategy_id") or ""),
            state=str(manifest.get("state") or ""),
            hypothesis_sha256=str(hypothesis_hash) if hypothesis_hash else None,
            implementation_sha256=(
                str(manifest.get("implementation_sha256"))
                if manifest.get("implementation_sha256")
                else None
            ),
            review_sha256=(
                str(manifest.get("review_sha256"))
                if manifest.get("review_sha256")
                else None
            ),
            validation_sha256=(
                str(manifest.get("validation_sha256"))
                if manifest.get("validation_sha256")
                else None
            ),
            allowed_for_paper=manifest.get("allowed_for_paper") is True,
            allowed_for_live_execution=False,
            integrity_ok=not blockers,
            blockers=tuple(sorted(set(blockers))),
        )

    def status(self) -> ResearchStatus:
        return self.verify_integrity()


def build_validation_payload(
    store: GovernedResearchStore,
    artifact_paths: Mapping[str, str | Path],
) -> dict[str, Any]:
    """Build a hash-pinned validation payload from one artifact per gate."""

    manifest = store._manifest()
    gates: dict[str, Any] = {}
    for gate in MANDATORY_GATES:
        if gate not in artifact_paths:
            continue
        path = Path(artifact_paths[gate]).expanduser().resolve()
        try:
            relative = path.relative_to(store.root).as_posix()
        except ValueError as exc:
            raise ResearchError(
                f"validation_artifact_outside_run:{gate}"
            ) from exc
        if not path.is_file():
            raise ResearchError(f"validation_artifact_missing:{gate}")
        gates[gate] = {
            "passed": True,
            "artifact": relative,
            "artifact_sha256": _sha256_file(path),
            "details": {},
        }
    return {
        "hypothesis_sha256": manifest.get("hypothesis_sha256"),
        "implementation_sha256": manifest.get("implementation_sha256"),
        "review_sha256": manifest.get("review_sha256"),
        "gates": gates,
    }


__all__ = [
    "ALLOWED_AGENTS",
    "AgentRole",
    "FORBIDDEN_PATH_PREFIXES",
    "GovernedResearchStore",
    "MANDATORY_GATES",
    "ResearchError",
    "ResearchState",
    "ResearchStatus",
    "SAFETY_ASSERTIONS",
    "build_validation_payload",
]
