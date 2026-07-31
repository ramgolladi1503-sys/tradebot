"""Single read-only runtime observer facade for the PR #748-#756 campaign."""

from __future__ import annotations

from pathlib import Path
import json
import os
import time
from typing import Any, Mapping

from core.unified_live_validation_pr748_756.campaign_contract import (
    COMPOSITION_SHA_ENV,
    ENABLE_ENV,
    EVIDENCE_ROOT_ENV,
    RUN_ID_ENV,
    CampaignIdentity,
    reject_presession_live_run_id,
)
from core.unified_live_validation_pr748_756.recorder import AppendOnlyRecorder
from core.unified_live_validation_pr748_756.seal import seal_evidence_root


_OBSERVER: "UnifiedLiveRuntimeObserver | None" = None


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return _truthy(source.get(ENABLE_ENV))


class UnifiedLiveRuntimeObserver:
    def __init__(self, identity: CampaignIdentity) -> None:
        self.identity = identity
        self.recorder = AppendOnlyRecorder(identity)
        self.root = Path(identity.evidence_root)
        self.live_root = self.root / "live"
        self.live_root.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._write_error_count = 0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "UnifiedLiveRuntimeObserver":
        source = os.environ if env is None else env
        if not _truthy(source.get(ENABLE_ENV)):
            raise RuntimeError("campaign_not_enabled")
        if not _truthy(source.get("TRADEBOT_READ_ONLY")):
            raise RuntimeError("campaign_requires_TRADEBOT_READ_ONLY_true")
        run_id = str(source.get(RUN_ID_ENV) or "").strip()
        evidence_root = str(source.get(EVIDENCE_ROOT_ENV) or "").strip()
        composition_sha = str(source.get(COMPOSITION_SHA_ENV) or "").strip()
        if not run_id or not evidence_root or not composition_sha:
            raise RuntimeError("campaign_identity_env_missing")
        reject_presession_live_run_id(run_id)
        identity = CampaignIdentity(
            run_id=run_id,
            schema_version=1,
            session_date="2026-07-31",
            campaign_commit_sha=str(source.get("UNIFIED_LIVE_VALIDATION_PR748_756_COMMIT_SHA") or ""),
            composition_manifest_sha=composition_sha,
            evidence_root=evidence_root,
        )
        return cls(identity)

    def write_process_identity(self, payload: Mapping[str, Any] | None = None) -> None:
        body = {
            "run_id": self.identity.run_id,
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "start_epoch": time.time(),
            "source": "main.py",
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
        body.update(dict(payload or {}))
        self._write_json("live/process_identity.json", body)
        self.record_heartbeat(event="runtime_observer_initialized")

    def record_heartbeat(self, *, event: str = "heartbeat") -> None:
        self._append(
            "live/heartbeat.jsonl",
            {
                "source": "runtime_observer",
                "event": event,
                "source_timestamp": time.time(),
                "receipt_timestamp": time.time(),
                "feed_session_id": None,
                "reconnect_generation": None,
                "symbol": None,
                "instrument_token": None,
                "source_provenance_type": "runtime_observer_lifecycle",
            },
            pr_number=750,
        )

    def observe_feed_truth(self, payload: Mapping[str, Any] | None, *, source: str) -> None:
        self._append("live/feed_truth_samples.jsonl", self._row(payload, source=source), pr_number=750)
        state = None
        if isinstance(payload, Mapping):
            state = payload.get("feed_truth_state") or payload.get("runtime_state") or payload.get("state")
        self._append(
            "live/feed_state_transitions.jsonl",
            self._row({"state": state, "payload": dict(payload or {})}, source=source),
            pr_number=750,
        )

    def observe_subscription(self, payload: Mapping[str, Any] | None, *, source: str) -> None:
        row = self._row(payload, source=source)
        self._append("live/subscription_events.jsonl", row, pr_number=749)
        self._append("live/subscription_registry_samples.jsonl", row, pr_number=750)

    def observe_constituent_source(self, metadata: Mapping[str, Any] | None, *, source: str) -> None:
        if not isinstance(metadata, Mapping):
            return
        refresh = metadata.get("market_event_graph_constituent_refresh")
        if isinstance(refresh, Mapping):
            self._append("live/constituent_source_refresh.jsonl", self._row(refresh, source=source), pr_number=749)
        evidence = metadata.get("market_event_graph_constituent_source_evidence")
        if isinstance(evidence, Mapping):
            self._append("live/constituent_source_states.jsonl", self._row(evidence, source=source), pr_number=749)
        self.observe_subscription(evidence if isinstance(evidence, Mapping) else {}, source=source)
        for row in list(metadata.get("completed_constituent_bars") or [])[-4:]:
            if isinstance(row, Mapping):
                self._append("live/constituent_completed_bars.jsonl", self._row(row, source=source), pr_number=749)
        preoutcome = {
            "source": source,
            "constituent_source_status": metadata.get("market_event_graph_constituent_source_status"),
            "constituent_source_reason": metadata.get("market_event_graph_constituent_source_reason"),
            "completed_bar_count": len(metadata.get("completed_constituent_bars") or []),
        }
        self._append("live/research_preoutcome_states.jsonl", self._row(preoutcome, source=source), pr_number=754)

    def observe_market_event_graph(self, observation: Mapping[str, Any] | None, *, source: str) -> None:
        if not isinstance(observation, Mapping):
            return
        self._append("live/market_event_graph_intervals.jsonl", self._row(observation, source=source), pr_number=748)
        self._append(
            "live/market_event_graph_states.jsonl",
            self._row(
                {
                    "status": observation.get("status"),
                    "reason": observation.get("reason"),
                    "graph_trigger_count": observation.get("graph_trigger_count"),
                    "partial_sequence_length": observation.get("partial_sequence_length"),
                },
                source=source,
            ),
            pr_number=748,
        )

    def observe_candidate_pool(self, report: Any, *, source: str) -> None:
        regime = getattr(report, "regime", None)
        if regime is not None:
            payload = regime.to_dict() if hasattr(regime, "to_dict") else getattr(regime, "__dict__", {})
            self._append("live/regime_outputs.jsonl", self._row(payload, source=source), pr_number=756)
        metadata = getattr(report, "metadata", {}) if isinstance(getattr(report, "metadata", {}), Mapping) else {}
        self.observe_market_event_graph(metadata.get("market_event_graph_runtime_observation"), source=source)
        for candidate in getattr(report, "candidates", ()) or ():
            payload = candidate.to_dict() if hasattr(candidate, "to_dict") else getattr(candidate, "__dict__", {})
            self._append("live/candidate_lineage.jsonl", self._row(payload, source=source), pr_number=756)
            self._append("live/execution_eligibility.jsonl", self._row(payload, source=source), pr_number=750)

    def observe_scoring_report(self, report: Any, *, source: str) -> None:
        for record in getattr(report, "scores", ()) or ():
            payload = record.to_dict() if hasattr(record, "to_dict") else getattr(record, "__dict__", {})
            self._append("live/regime_policy_decisions.jsonl", self._row(payload, source=source), pr_number=756)
            self._append("live/ranking_decisions.jsonl", self._row(payload, source=source), pr_number=756)
            self._append("live/phase1_decisions.jsonl", self._row(payload, source=source), pr_number=750)
            self._append("live/phase2_decisions.jsonl", self._row(payload, source=source), pr_number=750)
            self._append("live/execution_eligibility.jsonl", self._row(payload, source=source), pr_number=750)

    def observe_exception(self, exc: BaseException, *, source: str) -> None:
        self._append(
            "live/exceptions.jsonl",
            self._row({"error": f"{type(exc).__name__}:{exc}"}, source=source),
            pr_number=750,
        )

    def shutdown(self, *, seal: bool = True, state: str = "STOPPED") -> dict[str, Any]:
        if self._closed:
            return {"closed": True, "already_closed": True}
        self._closed = True
        accounting = {
            "run_id": self.identity.run_id,
            "state": state,
            "write_error_count": self._write_error_count,
            "end_epoch": time.time(),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
        self._write_json("postmarket/evidence_accounting.json", accounting)
        if seal and self._write_error_count == 0:
            try:
                manifest = seal_evidence_root(self.root)
                accounting["sealed"] = True
                accounting["artifact_manifest_sha256"] = manifest.get("artifact_manifest_sha256")
            except Exception as exc:
                accounting["sealed"] = False
                accounting["seal_error"] = f"{type(exc).__name__}:{exc}"
        else:
            accounting["sealed"] = False
        return accounting

    def _row(self, payload: Mapping[str, Any] | None, *, source: str) -> dict[str, Any]:
        row = dict(payload or {})
        row.setdefault("source_timestamp", time.time())
        row.setdefault("receipt_timestamp", time.time())
        row.setdefault("source", source)
        row.setdefault("feed_session_id", row.get("feed_session_id"))
        row.setdefault("reconnect_generation", row.get("reconnect_generation"))
        row.setdefault("symbol", row.get("symbol"))
        row.setdefault("instrument_token", row.get("instrument_token"))
        row.setdefault("source_provenance_type", source)
        return row

    def _append(self, relative_path: str, row: Mapping[str, Any], *, pr_number: int) -> None:
        if self._closed:
            return
        try:
            self.recorder.append(relative_path, row, pr_number=pr_number)
        except Exception:
            self._write_error_count += 1

    def _write_json(self, relative_path: str, payload: Mapping[str, Any]) -> None:
        try:
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        except Exception:
            self._write_error_count += 1


def init_from_env(env: Mapping[str, str] | None = None) -> UnifiedLiveRuntimeObserver | None:
    global _OBSERVER
    if not enabled(env):
        return None
    if _OBSERVER is None:
        _OBSERVER = UnifiedLiveRuntimeObserver.from_env(env)
    return _OBSERVER


def current() -> UnifiedLiveRuntimeObserver | None:
    return _OBSERVER


def shutdown_current(*, seal: bool = True, state: str = "STOPPED") -> dict[str, Any] | None:
    global _OBSERVER
    observer = _OBSERVER
    _OBSERVER = None
    if observer is None:
        return None
    return observer.shutdown(seal=seal, state=state)


def safe_call(method_name: str, *args: Any, **kwargs: Any) -> None:
    observer = current()
    if observer is None:
        return
    try:
        method = getattr(observer, method_name)
        method(*args, **kwargs)
    except Exception:
        try:
            observer._write_error_count += 1
        except Exception:
            pass
