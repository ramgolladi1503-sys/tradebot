from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd
import pyarrow.parquet as pq

_ALLOWED_DATA_SUFFIXES = {".parquet", ".csv", ".json", ".jsonl", ".md", ".txt"}
_ALLOWED_TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt"}
_REF_RE = re.compile(r"^[A-Za-z0-9._/@{}~^:+-]+$")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _parse_roots(raw: str | None) -> tuple[Path, ...]:
    if not raw:
        return ()
    values: list[Path] = []
    for value in raw.split(os.pathsep):
        value = value.strip()
        if value:
            values.append(Path(value).expanduser().resolve(strict=False))
    return tuple(values)


@dataclass(frozen=True)
class Settings:
    root: Path
    evidence_roots: tuple[Path, ...]
    data_roots: tuple[Path, ...]
    max_text_bytes: int = 5_000_000
    max_hash_bytes: int = 2_000_000_000
    max_result_rows: int = 100
    max_files: int = 500

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.getenv("TRADEBOT_ROOT", Path.cwd())).expanduser().resolve(strict=False)
        evidence = _parse_roots(os.getenv("TRADEBOT_EVIDENCE_ROOTS"))
        data = _parse_roots(os.getenv("TRADEBOT_DATA_ROOTS"))
        if not evidence:
            evidence = tuple(
                path.resolve(strict=False)
                for path in (root / "research", root / "runtime", root / "reports")
            )
        if not data:
            data = (root / "runtime",)
        return cls(
            root=root,
            evidence_roots=evidence,
            data_roots=data,
            max_text_bytes=int(os.getenv("TRADEBOT_MCP_MAX_TEXT_BYTES", "5000000")),
            max_hash_bytes=int(os.getenv("TRADEBOT_MCP_MAX_HASH_BYTES", "2000000000")),
            max_result_rows=int(os.getenv("TRADEBOT_MCP_MAX_RESULT_ROWS", "100")),
            max_files=int(os.getenv("TRADEBOT_MCP_MAX_FILES", "500")),
        )

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        roots = [self.root, *self.evidence_roots, *self.data_roots]
        unique: list[Path] = []
        for root in roots:
            resolved = root.resolve(strict=False)
            if resolved not in unique:
                unique.append(resolved)
        return tuple(unique)


class SafetyError(ValueError):
    """Raised when a requested path or operation violates the read-only boundary."""


class SafePathPolicy:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _is_secret_path(path: Path) -> bool:
        lowered = [part.lower() for part in path.parts]
        name = path.name.lower()
        if name == ".env" or name.startswith(".env."):
            return True
        if name in {"kite_access_token.pkl", "credentials.json", "service-account.json"}:
            return True
        if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            return True
        return any(part in {"secrets", "credentials"} for part in lowered)

    def resolve(
        self,
        value: str | Path,
        *,
        must_exist: bool = True,
        allow_directory: bool = False,
        suffixes: set[str] | None = None,
    ) -> Path:
        raw = Path(value).expanduser()
        candidate = raw if raw.is_absolute() else self.settings.root / raw
        resolved = candidate.resolve(strict=must_exist)
        if not any(_is_relative_to(resolved, root) for root in self.settings.allowed_roots):
            raise SafetyError(f"path escapes approved roots: {value}")
        if self._is_secret_path(resolved):
            raise SafetyError(f"secret-bearing path is blocked: {resolved.name}")
        if must_exist and not resolved.exists():
            raise FileNotFoundError(str(resolved))
        if resolved.exists() and resolved.is_dir() and not allow_directory:
            raise SafetyError(f"directory access is not allowed for this operation: {resolved}")
        if suffixes is not None and resolved.suffix.lower() not in suffixes:
            raise SafetyError(f"unsupported file type: {resolved.suffix}")
        return resolved

    def read_text(self, value: str | Path) -> str:
        path = self.resolve(value, suffixes=_ALLOWED_TEXT_SUFFIXES)
        size = path.stat().st_size
        if size > self.settings.max_text_bytes:
            raise SafetyError(f"text file exceeds limit: {size} bytes")
        return path.read_text(encoding="utf-8")


def sha256_file(path: Path, *, max_bytes: int | None = None) -> str:
    size = path.stat().st_size
    if max_bytes is not None and size > max_bytes:
        raise SafetyError(f"file exceeds hashing limit: {size} bytes")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class EvidenceService:
    CONTEXT_FILES = {
        "mission": "00_mission.md",
        "contract": "01_research_contract.md",
        "safety": "02_safety_boundaries.md",
        "data_authority": "03_data_authority.md",
        "pipeline_authority": "04_pipeline_authority.md",
        "hypothesis_queue": "05_hypothesis_queue.json",
        "consumed_evidence": "06_consumed_evidence_registry.json",
        "agent_registry": "07_agent_registry.json",
        "cycle_status": "08_cycle_status.json",
        "blockers": "10_unresolved_blockers.json",
        "candidate_freeze": "11_candidate_freeze_registry.json",
        "context_index": "12_context_index.md",
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.policy = SafePathPolicy(settings)

    def list_research_contexts(self) -> dict[str, Any]:
        contexts: list[dict[str, Any]] = []
        roots = (self.settings.root, *self.settings.evidence_roots)
        seen: set[Path] = set()
        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            patterns = ("research/**/context", "**/context") if root == self.settings.root else ("**/context",)
            for pattern in patterns:
                for path in root.glob(pattern):
                    resolved = path.resolve(strict=False)
                    if resolved in seen or not resolved.is_dir():
                        continue
                    seen.add(resolved)
                    cycle = resolved / self.CONTEXT_FILES["cycle_status"]
                    contexts.append(
                        {
                            "path": str(resolved),
                            "cycle_status_present": cycle.is_file(),
                            "modified_ns": max(
                                (child.stat().st_mtime_ns for child in resolved.iterdir() if child.is_file()),
                                default=0,
                            ),
                        }
                    )
                    if len(contexts) >= self.settings.max_files:
                        break
        contexts.sort(key=lambda item: item["modified_ns"], reverse=True)
        return {"contexts": contexts, "count": len(contexts)}

    def _context(self, context_dir: str | None) -> Path:
        if context_dir:
            return self.policy.resolve(context_dir, allow_directory=True)
        contexts = self.list_research_contexts()["contexts"]
        if not contexts:
            raise FileNotFoundError("no research context directory found")
        if len(contexts) > 1:
            raise SafetyError("multiple research contexts exist; pass context_dir explicitly")
        return Path(contexts[0]["path"])

    def _read_context(self, key: str, context_dir: str | None = None) -> dict[str, Any]:
        if key not in self.CONTEXT_FILES:
            raise KeyError(key)
        context = self._context(context_dir)
        path = context / self.CONTEXT_FILES[key]
        if not path.exists():
            return {"status": "MISSING", "path": str(path)}
        if path.suffix == ".json":
            return {
                "status": "PRESENT",
                "path": str(path),
                "sha256": sha256_file(path, max_bytes=self.settings.max_text_bytes),
                "content": load_json(path),
            }
        return {
            "status": "PRESENT",
            "path": str(path),
            "sha256": sha256_file(path, max_bytes=self.settings.max_text_bytes),
            "content": self.policy.read_text(path),
        }

    def get_research_status(self, context_dir: str | None = None) -> dict[str, Any]:
        return self._read_context("cycle_status", context_dir)

    def get_contract(self, context_dir: str | None = None) -> dict[str, Any]:
        return self._read_context("contract", context_dir)

    def get_safety_boundaries(self, context_dir: str | None = None) -> dict[str, Any]:
        return self._read_context("safety", context_dir)

    def get_consumed_evidence_registry(self, context_dir: str | None = None) -> dict[str, Any]:
        return self._read_context("consumed_evidence", context_dir)

    def get_holdout_status(self, context_dir: str | None = None) -> dict[str, Any]:
        status = self.get_research_status(context_dir)
        registry = self.get_consumed_evidence_registry(context_dir)
        return {"cycle_status": status, "consumed_evidence_registry": registry}

    def get_candidate_fingerprint(self, context_dir: str | None = None) -> dict[str, Any]:
        return self._read_context("candidate_freeze", context_dir)

    def list_agent_attempts(self, context_dir: str | None = None) -> dict[str, Any]:
        return self._read_context("agent_registry", context_dir)

    def list_agent_handoffs(self, context_dir: str | None = None) -> dict[str, Any]:
        context = self._context(context_dir)
        candidates = [context.parent / "handoffs", context / "handoffs"]
        results: list[dict[str, Any]] = []
        for directory in candidates:
            if not directory.exists() or not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in _ALLOWED_TEXT_SUFFIXES:
                    continue
                results.append(
                    {
                        "path": str(path.resolve()),
                        "size": path.stat().st_size,
                        "sha256": sha256_file(path, max_bytes=self.settings.max_text_bytes),
                    }
                )
                if len(results) >= self.settings.max_files:
                    break
        return {"handoffs": results, "count": len(results)}

    def get_agent_handoff(self, path: str) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes=_ALLOWED_TEXT_SUFFIXES)
        return {
            "path": str(resolved),
            "sha256": sha256_file(resolved, max_bytes=self.settings.max_text_bytes),
            "content": self.policy.read_text(resolved),
        }

    def list_source_manifests(self) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        keywords = ("manifest", "registry", "sidecar", "inventory", "authority", "hash")
        for root in self.settings.evidence_roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".txt"}:
                    continue
                if not any(keyword in path.name.lower() for keyword in keywords):
                    continue
                results.append({"path": str(path.resolve()), "size": path.stat().st_size})
                if len(results) >= self.settings.max_files:
                    return {"manifests": results, "truncated": True}
        return {"manifests": results, "truncated": False}

    def inspect_source_manifest(self, path: str) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes={".json"})
        return {
            "path": str(resolved),
            "sha256": sha256_file(resolved, max_bytes=self.settings.max_text_bytes),
            "content": load_json(resolved),
        }

    def verify_artifact_hash(self, path: str, expected_sha256: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise ValueError("expected_sha256 must contain exactly 64 hexadecimal characters")
        resolved = self.policy.resolve(path)
        actual = sha256_file(resolved, max_bytes=self.settings.max_hash_bytes)
        return {
            "path": str(resolved),
            "expected_sha256": expected_sha256.lower(),
            "actual_sha256": actual,
            "matches": actual == expected_sha256.lower(),
        }


class DataAuditService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.policy = SafePathPolicy(settings)

    def list_corpora(self, max_files: int | None = None) -> dict[str, Any]:
        limit = min(max_files or self.settings.max_files, self.settings.max_files)
        files: list[dict[str, Any]] = []
        for root in self.settings.data_roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in _ALLOWED_DATA_SUFFIXES:
                    continue
                if SafePathPolicy._is_secret_path(path):
                    continue
                files.append(
                    {
                        "path": str(path.resolve()),
                        "suffix": path.suffix.lower(),
                        "size": path.stat().st_size,
                    }
                )
                if len(files) >= limit:
                    return {"files": files, "truncated": True}
        return {"files": files, "truncated": False}

    def inspect_schema(self, path: str) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes={".parquet", ".csv"})
        if resolved.suffix.lower() == ".parquet":
            parquet = pq.ParquetFile(resolved)
            return {
                "path": str(resolved),
                "format": "parquet",
                "rows": parquet.metadata.num_rows,
                "row_groups": parquet.metadata.num_row_groups,
                "columns": [
                    {"name": field.name, "type": str(field.type)} for field in parquet.schema_arrow
                ],
            }
        sample = pd.read_csv(resolved, nrows=200)
        return {
            "path": str(resolved),
            "format": "csv",
            "sample_rows": len(sample),
            "columns": [{"name": name, "type": str(dtype)} for name, dtype in sample.dtypes.items()],
        }

    def hash_source(self, path: str) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes=_ALLOWED_DATA_SUFFIXES)
        return {
            "path": str(resolved),
            "size": resolved.stat().st_size,
            "sha256": sha256_file(resolved, max_bytes=self.settings.max_hash_bytes),
        }

    def count_rows(self, path: str) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes={".parquet", ".csv", ".jsonl"})
        suffix = resolved.suffix.lower()
        if suffix == ".parquet":
            rows = pq.ParquetFile(resolved).metadata.num_rows
        elif suffix == ".csv":
            with resolved.open("r", encoding="utf-8", newline="") as handle:
                rows = max(sum(1 for _ in handle) - 1, 0)
        else:
            with resolved.open("r", encoding="utf-8") as handle:
                rows = sum(1 for line in handle if line.strip())
        return {"path": str(resolved), "rows": int(rows)}

    def _timestamp_chunks(self, path: Path, timestamp_column: str) -> Iterator[pd.Series]:
        if path.suffix.lower() == ".parquet":
            parquet = pq.ParquetFile(path)
            if timestamp_column not in parquet.schema_arrow.names:
                raise KeyError(f"missing timestamp column: {timestamp_column}")
            for batch in parquet.iter_batches(columns=[timestamp_column], batch_size=100_000):
                yield pd.to_datetime(batch.column(0).to_pandas(), utc=True, errors="raise")
            return
        for chunk in pd.read_csv(path, usecols=[timestamp_column], chunksize=100_000):
            yield pd.to_datetime(chunk[timestamp_column], utc=True, errors="raise")

    def count_sessions(
        self,
        path: str,
        timestamp_column: str,
        timezone: str = "Asia/Kolkata",
    ) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes={".parquet", ".csv"})
        counts: dict[str, int] = {}
        total = 0
        for timestamps in self._timestamp_chunks(resolved, timestamp_column):
            local_dates = timestamps.dt.tz_convert(timezone).dt.date.astype(str)
            for session, count in local_dates.value_counts().items():
                counts[str(session)] = counts.get(str(session), 0) + int(count)
            total += len(timestamps)
        ordered = dict(sorted(counts.items()))
        return {
            "path": str(resolved),
            "timezone": timezone,
            "rows": total,
            "session_count": len(ordered),
            "sessions": ordered,
        }

    def audit_duplicates(self, path: str, timestamp_column: str) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes={".parquet", ".csv"})
        seen: set[int] = set()
        duplicates = 0
        rows = 0
        samples: list[str] = []
        for timestamps in self._timestamp_chunks(resolved, timestamp_column):
            for value in timestamps:
                nanos = int(value.value)
                if nanos in seen:
                    duplicates += 1
                    if len(samples) < 10:
                        samples.append(value.isoformat())
                else:
                    seen.add(nanos)
                rows += 1
        return {
            "path": str(resolved),
            "rows": rows,
            "duplicate_timestamps": duplicates,
            "sample_duplicates": samples,
        }

    def audit_timestamp_order(self, path: str, timestamp_column: str) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes={".parquet", ".csv"})
        previous: pd.Timestamp | None = None
        violations = 0
        duplicates = 0
        rows = 0
        samples: list[dict[str, str]] = []
        first: str | None = None
        last: str | None = None
        for timestamps in self._timestamp_chunks(resolved, timestamp_column):
            for value in timestamps:
                if first is None:
                    first = value.isoformat()
                if previous is not None:
                    if value < previous:
                        violations += 1
                        if len(samples) < 10:
                            samples.append({"previous": previous.isoformat(), "current": value.isoformat()})
                    elif value == previous:
                        duplicates += 1
                previous = value
                last = value.isoformat()
                rows += 1
        return {
            "path": str(resolved),
            "rows": rows,
            "first_timestamp": first,
            "last_timestamp": last,
            "order_violations": violations,
            "adjacent_duplicates": duplicates,
            "sample_violations": samples,
            "monotonic_non_decreasing": violations == 0,
        }

    def audit_missing_intervals(
        self,
        path: str,
        timestamp_column: str,
        expected_seconds: float,
    ) -> dict[str, Any]:
        if expected_seconds <= 0:
            raise ValueError("expected_seconds must be positive")
        resolved = self.policy.resolve(path, suffixes={".parquet", ".csv"})
        previous: pd.Timestamp | None = None
        gaps = 0
        max_gap = 0.0
        samples: list[dict[str, Any]] = []
        for timestamps in self._timestamp_chunks(resolved, timestamp_column):
            for value in timestamps:
                if previous is not None:
                    delta = (value - previous).total_seconds()
                    if delta > expected_seconds:
                        gaps += 1
                        max_gap = max(max_gap, delta)
                        if len(samples) < 20:
                            samples.append(
                                {
                                    "previous": previous.isoformat(),
                                    "current": value.isoformat(),
                                    "gap_seconds": delta,
                                }
                            )
                previous = value
        return {
            "path": str(resolved),
            "expected_seconds": expected_seconds,
            "gap_count": gaps,
            "max_gap_seconds": max_gap,
            "sample_gaps": samples,
        }

    def sample_session(
        self,
        path: str,
        timestamp_column: str,
        session_date: str,
        timezone: str = "Asia/Kolkata",
        columns: Sequence[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        resolved = self.policy.resolve(path, suffixes={".parquet", ".csv"})
        limit = max(1, min(limit, self.settings.max_result_rows))
        requested = list(dict.fromkeys([timestamp_column, *(columns or [])]))
        frames: list[pd.DataFrame] = []
        if resolved.suffix.lower() == ".parquet":
            parquet = pq.ParquetFile(resolved)
            missing = [name for name in requested if name not in parquet.schema_arrow.names]
            if missing:
                raise KeyError(f"missing columns: {missing}")
            batches: Iterable[Any] = parquet.iter_batches(columns=requested, batch_size=50_000)
            frame_iter = (batch.to_pandas() for batch in batches)
        else:
            frame_iter = pd.read_csv(resolved, usecols=requested, chunksize=50_000)
        for frame in frame_iter:
            timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors="raise")
            mask = timestamps.dt.tz_convert(timezone).dt.date.astype(str) == session_date
            selected = frame.loc[mask].copy()
            if not selected.empty:
                selected[timestamp_column] = timestamps.loc[mask].astype(str)
                frames.append(selected)
            if sum(len(item) for item in frames) >= limit:
                break
        result = pd.concat(frames, ignore_index=True).head(limit) if frames else pd.DataFrame(columns=requested)
        return {
            "path": str(resolved),
            "session_date": session_date,
            "timezone": timezone,
            "rows": json.loads(result.to_json(orient="records", date_format="iso")),
            "count": len(result),
        }

    def audit_join_causality(
        self,
        left_path: str,
        right_path: str,
        left_timestamp: str,
        right_timestamp: str,
        tolerance_seconds: float,
        max_rows: int = 500_000,
    ) -> dict[str, Any]:
        if tolerance_seconds < 0:
            raise ValueError("tolerance_seconds cannot be negative")
        left = self.policy.resolve(left_path, suffixes={".parquet", ".csv"})
        right = self.policy.resolve(right_path, suffixes={".parquet", ".csv"})
        left_values = self._read_timestamp_sample(left, left_timestamp, max_rows)
        right_values = self._read_timestamp_sample(right, right_timestamp, max_rows)
        left_frame = pd.DataFrame({"left_ts": left_values}).sort_values("left_ts")
        right_frame = pd.DataFrame({"right_ts": right_values}).sort_values("right_ts")
        joined = pd.merge_asof(
            left_frame,
            right_frame,
            left_on="left_ts",
            right_on="right_ts",
            direction="backward",
            tolerance=pd.Timedelta(seconds=tolerance_seconds),
        )
        matched = joined["right_ts"].notna()
        future = matched & (joined["right_ts"] > joined["left_ts"])
        lag = (joined.loc[matched, "left_ts"] - joined.loc[matched, "right_ts"]).dt.total_seconds()
        return {
            "left_path": str(left),
            "right_path": str(right),
            "left_rows": len(left_frame),
            "right_rows": len(right_frame),
            "matched_rows": int(matched.sum()),
            "unmatched_rows": int((~matched).sum()),
            "future_matches": int(future.sum()),
            "max_lag_seconds": float(lag.max()) if not lag.empty else None,
            "causal": int(future.sum()) == 0,
            "truncated": len(left_values) >= max_rows or len(right_values) >= max_rows,
        }

    @staticmethod
    def _read_timestamp_sample(path: Path, column: str, max_rows: int) -> pd.Series:
        if path.suffix.lower() == ".parquet":
            table = pq.read_table(path, columns=[column]).slice(0, max_rows)
            return pd.to_datetime(table.column(0).to_pandas(), utc=True, errors="raise")
        frame = pd.read_csv(path, usecols=[column], nrows=max_rows)
        return pd.to_datetime(frame[column], utc=True, errors="raise")


GATE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "bootstrap": (
        "mission",
        "research_contract",
        "safety_boundaries",
        "context_hashes",
        "holdout_locked",
        "fresh_confirmation_locked",
    ),
    "wave1": (
        "source_authority",
        "pipeline_static",
        "pipeline_synthetic",
        "pipeline_real_data",
        "statistics_infrastructure",
        "microstructure_disposition",
        "consumed_evidence_registry",
        "holdout_locked",
        "fresh_confirmation_locked",
    ),
    "temporal": (
        "completed_candle",
        "next_bar_entry",
        "future_mutation_invariance",
        "session_boundary",
        "timestamp_order",
        "deterministic_replay",
    ),
    "candidate_freeze": (
        "hypothesis_contract_hash",
        "session_universe_hash",
        "candidate_fingerprint",
        "wfa_folds_hash",
        "negative_controls",
        "multiple_testing",
        "holdout_locked",
    ),
    "wfa": (
        "chronological_folds",
        "purge_embargo",
        "cost_adjusted_metrics",
        "fold_metrics",
        "concentration",
        "latency",
        "controls",
    ),
    "determinism": ("run_a_hash", "run_b_hash", "semantic_equality"),
    "oracle": (
        "independent_implementation",
        "sample_reconciliation",
        "aggregate_reconciliation",
        "perturbation_failure",
    ),
    "publication": (
        "candidate_freeze_gate",
        "wfa_gate",
        "determinism_gate",
        "oracle_gate",
        "fresh_oos_confirmation",
        "no_production_changes",
    ),
}


class GateService:
    """Fail-closed evaluator for machine-generated evidence manifests.

    The service never runs arbitrary shell commands. Each PASS check must point to
    a hash-verified artifact and must record the producing command, exit code and
    commit. Narrative status strings are ignored.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.policy = SafePathPolicy(settings)

    def evaluate(self, gate_name: str, evidence_path: str) -> dict[str, Any]:
        if gate_name not in GATE_REQUIREMENTS:
            raise ValueError(f"unsupported gate: {gate_name}")
        evidence_file = self.policy.resolve(evidence_path, suffixes={".json"})
        evidence = load_json(evidence_file)
        if evidence.get("schema_version") != 1:
            return self._failure(gate_name, evidence_file, ["schema_version must equal 1"])
        gates = evidence.get("gates")
        if not isinstance(gates, dict) or gate_name not in gates:
            return self._failure(gate_name, evidence_file, ["gate record is missing"])
        checks = gates[gate_name].get("checks") if isinstance(gates[gate_name], dict) else None
        if not isinstance(checks, dict):
            return self._failure(gate_name, evidence_file, ["checks must be an object"])
        failures: list[str] = []
        results: dict[str, Any] = {}
        for check_id in GATE_REQUIREMENTS[gate_name]:
            check = checks.get(check_id)
            if not isinstance(check, dict):
                failures.append(f"{check_id}: missing check")
                continue
            result = self._evaluate_check(check_id, check)
            results[check_id] = result
            if not result["valid"]:
                failures.extend(f"{check_id}: {reason}" for reason in result["reasons"])
        extra = sorted(set(checks) - set(GATE_REQUIREMENTS[gate_name]))
        return {
            "gate": gate_name,
            "verdict": "PASS" if not failures else "FAIL",
            "evidence_path": str(evidence_file),
            "evidence_sha256": sha256_file(evidence_file, max_bytes=self.settings.max_text_bytes),
            "required_checks": list(GATE_REQUIREMENTS[gate_name]),
            "checks": results,
            "extra_checks_ignored": extra,
            "failures": failures,
        }

    def _evaluate_check(self, check_id: str, check: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        if check.get("status") != "PASS":
            reasons.append("status is not PASS")
        if check.get("exit_code") != 0:
            reasons.append("exit_code is not 0")
        command = check.get("command")
        if not isinstance(command, str) or not command.strip():
            reasons.append("producing command is missing")
        commit = check.get("producer_commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit):
            reasons.append("producer_commit is missing or invalid")
        artifact_value = check.get("artifact")
        expected_hash = check.get("sha256")
        actual_hash: str | None = None
        artifact_path: str | None = None
        if not isinstance(artifact_value, str) or not artifact_value:
            reasons.append("artifact path is missing")
        elif not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            reasons.append("artifact sha256 is missing or invalid")
        else:
            try:
                artifact = self.policy.resolve(artifact_value)
                artifact_path = str(artifact)
                actual_hash = sha256_file(artifact, max_bytes=self.settings.max_hash_bytes)
                if actual_hash != expected_hash.lower():
                    reasons.append("artifact hash mismatch")
            except (OSError, SafetyError) as exc:
                reasons.append(str(exc))
        return {
            "check_id": check_id,
            "valid": not reasons,
            "artifact": artifact_path,
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "reasons": reasons,
        }

    @staticmethod
    def _failure(gate_name: str, evidence_file: Path, failures: list[str]) -> dict[str, Any]:
        return {
            "gate": gate_name,
            "verdict": "FAIL",
            "evidence_path": str(evidence_file),
            "required_checks": list(GATE_REQUIREMENTS[gate_name]),
            "checks": {},
            "failures": failures,
        }

    def evaluate_all(self, evidence_path: str) -> dict[str, Any]:
        results = {name: self.evaluate(name, evidence_path) for name in GATE_REQUIREMENTS}
        return {
            "verdict": "PASS" if all(item["verdict"] == "PASS" for item in results.values()) else "FAIL",
            "gates": results,
        }


class GitAuditService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.root
        if not (self.root / ".git").exists() and not (self.root / ".git").is_file():
            raise SafetyError(f"not a git worktree: {self.root}")

    def _git(self, *args: str, timeout: int = 20) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return completed.stdout

    @staticmethod
    def _validate_ref(value: str) -> str:
        if not _REF_RE.fullmatch(value):
            raise SafetyError(f"invalid git ref: {value}")
        return value

    def get_worktree_status(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "branch": self._git("branch", "--show-current").strip(),
            "head": self._git("rev-parse", "HEAD").strip(),
            "status": self._git("status", "--short", "--branch").splitlines(),
        }

    def list_worktrees(self) -> dict[str, Any]:
        raw = self._git("worktree", "list", "--porcelain")
        entries: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for line in raw.splitlines():
            if not line:
                if current:
                    entries.append(current)
                    current = {}
                continue
            key, _, value = line.partition(" ")
            if key in {"bare", "detached", "locked", "prunable"} and not value:
                current[key] = True
            else:
                current[key] = value
        if current:
            entries.append(current)
        return {"worktrees": entries}

    def get_branch_head(self, ref: str = "HEAD") -> dict[str, Any]:
        ref = self._validate_ref(ref)
        return {"ref": ref, "sha": self._git("rev-parse", ref).strip()}

    def get_changed_files(self, base: str | None = None, head: str = "HEAD") -> dict[str, Any]:
        head = self._validate_ref(head)
        if base:
            base = self._validate_ref(base)
            raw = self._git("diff", "--name-status", f"{base}...{head}")
            comparison = f"{base}...{head}"
        else:
            raw = self._git("status", "--porcelain")
            comparison = "worktree"
        changes: list[dict[str, str]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            status, _, path = line.partition("\t")
            if not path:
                status, path = line[:2].strip(), line[3:]
            changes.append({"status": status.strip(), "path": path.strip()})
        return {"comparison": comparison, "changes": changes}

    def scan_prohibited_paths(
        self,
        base: str,
        head: str = "HEAD",
        prohibited_prefixes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        prohibited = tuple(
            prohibited_prefixes
            or (
                "core/broker",
                "core/execution",
                "core/risk",
                "dashboard/",
                "config/",
                ".env",
                "main.py",
            )
        )
        changed = self.get_changed_files(base, head)["changes"]
        hits = [item for item in changed if item["path"].startswith(prohibited)]
        return {"prohibited_prefixes": list(prohibited), "hits": hits, "passes": not hits}

    def verify_commit_scope(
        self,
        base: str,
        head: str,
        allowed_prefixes: Sequence[str],
        prohibited_prefixes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if not allowed_prefixes:
            raise ValueError("allowed_prefixes cannot be empty")
        changed = self.get_changed_files(base, head)["changes"]
        outside = [item for item in changed if not item["path"].startswith(tuple(allowed_prefixes))]
        prohibited = self.scan_prohibited_paths(base, head, prohibited_prefixes)["hits"]
        return {
            "allowed_prefixes": list(allowed_prefixes),
            "changed": changed,
            "outside_allowed_scope": outside,
            "prohibited_hits": prohibited,
            "passes": not outside and not prohibited,
        }

    def check_worktree_clean(self) -> dict[str, Any]:
        lines = [line for line in self._git("status", "--porcelain").splitlines() if line.strip()]
        return {"clean": not lines, "changes": lines}
