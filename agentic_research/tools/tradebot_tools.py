from __future__ import annotations

import csv
import hashlib
import importlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from agentic_research.certification import DeterministicCertificationJudge
from agentic_research.contracts import CertificationDecision, CriticReport, ToolResult, load_config
from agentic_research.critics import DeterministicAdversarialCritic
from agentic_research.hypotheses import BoundedHypothesisProposer
from agentic_research.memory import HypothesisRegistry
from agentic_research.storage import ArtifactStore


class TradeBotReadOnlyTools:
    TOOL_NAMES = (
        "get_strategy_contract",
        "validate_dataset",
        "audit_existing_research_report",
        "run_temporal_semantics_tests",
        "run_structural_backtest",
        "run_wfa",
        "run_adversarial_review",
        "create_certification_bundle",
        "propose_next_hypotheses",
    )

    def __init__(self, repo_root: Path, sidecar_root: Path | None = None, runs_root: Path | None = None, critic=None, hypothesis_registry=None, hypothesis_proposer=None):
        self.repo_root = Path(repo_root).resolve()
        self.sidecar_root = (Path(sidecar_root) if sidecar_root else self.repo_root / "agentic_research").resolve()
        self.config_root = self.sidecar_root / "config"
        self.store = ArtifactStore(runs_root or self.sidecar_root / "runs")
        self.critic = critic or DeterministicAdversarialCritic()
        self.hypothesis_registry = hypothesis_registry or HypothesisRegistry(self.sidecar_root / ".state" / "hypotheses.sqlite")
        self.hypothesis_proposer = hypothesis_proposer or BoundedHypothesisProposer()

    def get_strategy_contract(self, research_id: str, strategy_id: str) -> ToolResult:
        spec = load_config(self.config_root / "strategy_spec.yaml")
        blockers: list[str] = []
        if spec.get("strategy_id") != strategy_id:
            blockers.append("strategy_id_contract_mismatch")
        source = self.repo_root / str(spec.get("source_path"))
        source_hash = self._sha256_file(source) if source.exists() else None
        if source_hash is None:
            blockers.append("strategy_source_missing")
        payload = {"contract": spec, "source_hash": source_hash, "read_only": True}
        return self._persist(research_id, "get_strategy_contract", ToolResult(tool="get_strategy_contract", status="SUCCESS" if not blockers else "REJECTED", payload=payload, blockers=blockers))

    def validate_dataset(self, research_id: str, dataset_path: str) -> ToolResult:
        requirements = load_config(self.config_root / "dataset_requirements.yaml")
        path = Path(dataset_path).expanduser().resolve()
        blockers: list[str] = []
        if not path.exists() or not path.is_file():
            return self._persist(research_id, "validate_dataset", ToolResult(tool="validate_dataset", status="REJECTED", payload={"dataset_path": str(path)}, blockers=["dataset_not_found"]))
        try:
            rows = list(self._read_rows(path))
        except Exception as exc:
            return self._persist(research_id, "validate_dataset", ToolResult(tool="validate_dataset", status="ERROR", payload={"dataset_path": str(path), "error": str(exc)}, blockers=["dataset_unreadable"]))
        if not rows:
            blockers.append("dataset_empty")
        required = list(requirements.get("required_top_level_fields") or [])
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                blockers.append(f"row_not_object:{index}")
                continue
            for field in required:
                if field not in row or row[field] is None:
                    blockers.append(f"missing_field:{field}:row:{index}")
            context = self._decode_json_cell(row.get("context"))
            if not isinstance(context, dict):
                blockers.append(f"context_not_object:row:{index}")
            else:
                for field in requirements.get("required_context_fields") or []:
                    if context.get(field) is None:
                        blockers.append(f"missing_context_field:{field}:row:{index}")
            regime = self._decode_json_cell(row.get("regime"))
            if not isinstance(regime, dict):
                blockers.append(f"regime_not_object:row:{index}")
            else:
                for field in requirements.get("required_regime_fields") or []:
                    if regime.get(field) is None:
                        blockers.append(f"missing_regime_field:{field}:row:{index}")
            if row.get("split") not in set(requirements.get("allowed_splits") or []):
                blockers.append(f"invalid_split:row:{index}")
            try:
                float(row.get("forward_return_bps"))
            except Exception:
                blockers.append(f"forward_return_not_numeric:row:{index}")
        timestamps = [str(row.get("timestamp")) for row in rows if isinstance(row, dict) and row.get("timestamp") is not None]
        if requirements.get("require_unique_timestamp") and len(timestamps) != len(set(timestamps)):
            blockers.append("duplicate_timestamps")
        if requirements.get("require_monotonic_timestamp") and timestamps != sorted(timestamps):
            blockers.append("timestamps_not_monotonic")
        payload = {
            "dataset_path": str(path),
            "dataset_hash": self._sha256_file(path),
            "row_count": len(rows),
            "columns": sorted({key for row in rows if isinstance(row, dict) for key in row}),
            "requirements": requirements,
            "volume_dependent_claims_allowed": False,
            "option_execution_claims_allowed": False,
        }
        blockers = sorted(set(blockers))
        return self._persist(research_id, "validate_dataset", ToolResult(tool="validate_dataset", status="SUCCESS" if not blockers else "REJECTED", payload=payload, blockers=blockers))

    def audit_existing_research_report(self, research_id: str, report_path: str, strategy_id: str = "trend_pullback_v1") -> ToolResult:
        path = Path(report_path).expanduser().resolve()
        if not path.exists():
            return self._persist(research_id, "audit_existing_research_report", ToolResult(tool="audit_existing_research_report", status="REJECTED", blockers=["legacy_report_not_found"], payload={"report_path": str(path)}))
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._persist(research_id, "audit_existing_research_report", ToolResult(tool="audit_existing_research_report", status="ERROR", blockers=["legacy_report_unreadable"], payload={"error": str(exc)}))
        blockers: list[str] = []
        movement_name = f"movement.{strategy_id}"
        if movement_name in set(report.get("invalid_volume_or_vwap_assumption") or []):
            blockers.append("legacy_data_invalid_for_volume_or_vwap_assumption")
        if str(report.get("inspection", {}).get("volume_quality")) == "ZERO_VOLUME":
            blockers.append("legacy_dataset_zero_volume")
        if str(report.get("entry_rule")) == "current_candle_close":
            blockers.append("legacy_same_bar_proxy_entry")
        if "NOT_EXECUTABLE_OPTION_BACKTEST" in str(report.get("verdict")):
            blockers.append("legacy_report_not_executable_option_evidence")
        payload = {
            "report_path": str(path),
            "report_hash": self._sha256_file(path),
            "report_date": report.get("date"),
            "strategy_id": strategy_id,
            "source_verdict": report.get("verdict"),
            "entry_rule": report.get("entry_rule"),
            "volume_quality": report.get("inspection", {}).get("volume_quality"),
            "read_only": True,
        }
        return self._persist(research_id, "audit_existing_research_report", ToolResult(tool="audit_existing_research_report", status="REJECTED" if blockers else "SUCCESS", payload=payload, blockers=sorted(set(blockers))))

    def run_temporal_semantics_tests(self, research_id: str) -> ToolResult:
        command = [sys.executable, "-m", "pytest", "tests/test_trend_pullback_temporal_semantics.py", "-q"]
        completed = subprocess.run(command, cwd=self.repo_root, text=True, capture_output=True, timeout=180, check=False)
        payload = {"command": command, "exit_code": completed.returncode, "stdout": completed.stdout[-12000:], "stderr": completed.stderr[-12000:], "causality_violations": 0 if completed.returncode == 0 else 1}
        return self._persist(research_id, "run_temporal_semantics_tests", ToolResult(tool="run_temporal_semantics_tests", status="SUCCESS" if completed.returncode == 0 else "REJECTED", payload=payload, blockers=[] if completed.returncode == 0 else ["temporal_semantics_tests_failed"]))

    def run_structural_backtest(self, research_id: str, dataset_path: str, split: str | None = None, artifact_name: str = "baseline_result") -> ToolResult:
        validation = self.validate_dataset(research_id, dataset_path)
        if validation.status != "SUCCESS":
            return self._persist(research_id, artifact_name, ToolResult(tool="run_structural_backtest", status="REJECTED", blockers=["dataset_ineligible_for_backtest"]))
        frozen = load_config(self.config_root / "frozen_parameters.json")
        rows = list(self._read_rows(Path(dataset_path).expanduser().resolve()))
        if split is not None:
            rows = [row for row in rows if row.get("split") == split]
        context_from_dict = self._resolve("core.movement_contract.context_from_dict")
        regime_type = self._resolve("core.movement_regime.MovementRegimeResult")
        strategy_callable = self._resolve("strategies.movement.trend_pullback.generate_trend_pullback_candidates")
        trade_returns: list[float] = []
        candidate_rows: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            context_payload = self._decode_json_cell(row.get("context"))
            regime_payload = self._decode_json_cell(row.get("regime"))
            ctx = context_from_dict(context_payload)
            regime = regime_type(schema_version=int(regime_payload.get("schema_version", 1)), primary_regime=regime_payload["primary_regime"], scores=regime_payload["scores"], warnings=tuple(regime_payload.get("warnings") or ()), evidence=dict(regime_payload.get("evidence") or {}))
            for candidate in strategy_callable(ctx, regime):
                signed = float(row["forward_return_bps"])
                gross = signed if candidate.direction == "BUY_CALL" else -signed
                net = gross - float(frozen.get("round_trip_cost_bps", 0.0))
                trade_returns.append(net)
                candidate_rows.append({"row_index": index, "timestamp": row.get("timestamp"), "split": row.get("split"), "direction": candidate.direction, "raw_score": candidate.raw_score, "net_return_bps": net, "setup_identity": candidate.evidence.get("setup_identity")})
        payload = {**self._metrics(trade_returns), "split": split or "all", "candidate_rows": candidate_rows, "dataset_hash": validation.payload.get("dataset_hash"), "frozen_parameters": frozen, "engine": "actual_trend_pullback_callable_structural_replay", "option_execution_certified": False}
        return self._persist(research_id, artifact_name, ToolResult(tool="run_structural_backtest", status="SUCCESS", payload=payload))

    def run_wfa(self, research_id: str, dataset_path: str) -> ToolResult:
        partitions: dict[str, dict[str, Any]] = {}
        positive = 0
        for split in ("train", "validation", "holdout"):
            result = self.run_structural_backtest(research_id, dataset_path, split=split, artifact_name=f"wfa_{split}")
            if result.status != "SUCCESS":
                return self._persist(research_id, "run_wfa", ToolResult(tool="run_wfa", status="REJECTED", blockers=[f"partition_failed:{split}"]))
            partitions[split] = {key: value for key, value in result.payload.items() if key != "candidate_rows"}
            if split in {"validation", "holdout"} and float(result.payload.get("net_expectancy_bps") or 0.0) > 0.0:
                positive += 1
        payload = {**partitions, "positive_oos_partition_fraction": positive / 2.0, "partition_order": ["train", "validation", "holdout"], "purged_embargoed_option_wfa_used": False, "structural_mvp_only": True}
        return self._persist(research_id, "run_wfa", ToolResult(tool="run_wfa", status="SUCCESS", payload=payload))

    def run_adversarial_review(self, research_id: str, results: dict[str, ToolResult]) -> ToolResult:
        report: CriticReport = self.critic.review(results)
        return self._persist(research_id, "run_adversarial_review", ToolResult(tool="run_adversarial_review", status="SUCCESS", payload={"report": report.model_dump(mode="json")}, blockers=[finding.code for finding in report.blockers]))

    def propose_next_hypotheses(self, research_id: str, strategy_id: str, results: dict[str, ToolResult]) -> ToolResult:
        dataset_hash = "unknown"
        for source_name in ("validate_dataset", "audit_existing_research_report"):
            source = results.get(source_name)
            if source:
                dataset_hash = str(source.payload.get("dataset_hash") or source.payload.get("report_hash") or "unknown")
                break
        proposals = self.hypothesis_proposer.propose(strategy_id, dataset_hash, results)
        created: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        for proposal in proposals[:3]:
            is_new, stored = self.hypothesis_registry.register(proposal)
            (created if is_new else duplicates).append(stored.model_dump(mode="json"))
        payload = {"strategy_id": strategy_id, "maximum_proposals": 3, "created": created, "duplicates": duplicates, "strategy_code_modified": False, "human_approval_required_before_experiment": True}
        return self._persist(research_id, "propose_next_hypotheses", ToolResult(tool="propose_next_hypotheses", status="SUCCESS", payload=payload))

    def create_certification_bundle(self, research_id: str, results: dict[str, ToolResult]) -> ToolResult:
        gates = load_config(self.config_root / "certification_gates.yaml")
        decision: CertificationDecision = DeterministicCertificationJudge(gates).decide(results)
        _, decision_hash = self.store.write_json(research_id, "certification_result.json", decision.model_dump(mode="json"))
        manifest = {"research_id": research_id, "decision": decision.model_dump(mode="json"), "artifacts": sorted(path.name for path in self.store.run_dir(research_id).iterdir() if path.is_file()), "read_only": True, "production_architecture_modified": False}
        bundle_path, bundle_hash = self.store.write_json(research_id, "certification_bundle.json", manifest)
        return ToolResult(tool="create_certification_bundle", status="SUCCESS", payload={"decision": decision.model_dump(mode="json"), "decision_hash": decision_hash, "bundle_hash": bundle_hash}, artifact_path=str(bundle_path), result_hash=bundle_hash)

    def _persist(self, research_id: str, name: str, result: ToolResult) -> ToolResult:
        hashed = result.with_hash()
        path, digest = self.store.write_json(research_id, f"{name}.json", hashed.model_dump(mode="json"))
        return hashed.model_copy(update={"artifact_path": str(path), "result_hash": digest})

    @staticmethod
    def _resolve(dotted: str) -> Any:
        module_name, attribute = dotted.rsplit(".", 1)
        return getattr(importlib.import_module(module_name), attribute)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _decode_json_cell(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def _read_rows(self, path: Path) -> Iterable[dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        yield json.loads(line)
            return
        if suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            rows = value.get("rows") if isinstance(value, dict) else value
            if not isinstance(rows, list):
                raise ValueError("json_dataset_must_be_list_or_rows_object")
            yield from rows
            return
        if suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                yield from csv.DictReader(handle)
            return
        if suffix in {".parquet", ".pq"}:
            import pandas as pd
            yield from pd.read_parquet(path).to_dict(orient="records")
            return
        raise ValueError(f"unsupported_dataset_format:{suffix}")

    @staticmethod
    def _metrics(returns: list[float]) -> dict[str, Any]:
        if not returns:
            return {"trades": 0, "net_expectancy_bps": None, "profit_factor": None, "wins": 0, "losses": 0, "net_pnl_bps": 0.0}
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = math.inf if gross_loss == 0 and gross_win > 0 else (gross_win / gross_loss if gross_loss else None)
        return {"trades": len(returns), "net_expectancy_bps": sum(returns) / len(returns), "profit_factor": profit_factor, "wins": len(wins), "losses": len(losses), "net_pnl_bps": sum(returns)}
