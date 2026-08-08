#!/usr/bin/env python3
"""Local, allowlisted execution bridge for MROS reviewer/auditor jobs.

This module is intentionally narrow:
- no arbitrary shell command API;
- no broker/runtime actions;
- only preconfigured model backends may execute;
- every job is bound to an exact Git candidate SHA;
- every job receives a fresh detached worktree and process environment;
- reviewer/auditor outputs are isolated by role/job id;
- immutable JSONL job events are recorded locally.

It is an execution substrate only. It does NOT declare reviewer independence,
aggregate findings, accept sprints, grant authority, or advance MROS state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
ROLE_RE = re.compile(r"^(R|A)[0-9]{2,3}$")
JOB_TYPES = {"reviewer", "auditor"}
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}


class BridgeError(RuntimeError):
    """Controlled bridge error."""


@dataclass(frozen=True)
class BackendSpec:
    name: str
    argv_template: tuple[str, ...]
    timeout_seconds: int = 3600

    def render(self, *, worktree: Path, packet: Path, output: Path) -> list[str]:
        values = {
            "worktree": str(worktree),
            "packet": str(packet),
            "output": str(output),
        }
        rendered = [part.format(**values) for part in self.argv_template]
        if not rendered or not rendered[0].strip():
            raise BridgeError("BACKEND_COMMAND_EMPTY")
        return rendered


@dataclass(frozen=True)
class BridgeConfig:
    repo_root: Path
    worktree_root: Path
    state_root: Path
    allowed_repo_realpath: Path
    backends: Mapping[str, BackendSpec]
    max_parallel_jobs: int = 4


@dataclass
class JobRecord:
    job_id: str
    job_type: str
    role_id: str
    candidate_sha: str
    packet_path: str
    output_path: str
    backend: str
    state: str = "QUEUED"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    command_hash: str | None = None
    worktree_path: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.jobs_dir = state_root / "jobs"
        self.events_path = state_root / "events.jsonl"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def save(self, record: JobRecord) -> None:
        payload = json.dumps(record.public_dict(), sort_keys=True, indent=2) + "\n"
        path = self._job_path(record.job_id)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)

    def load(self, job_id: str) -> JobRecord:
        path = self._job_path(job_id)
        if not path.exists():
            raise BridgeError("JOB_NOT_FOUND")
        return JobRecord(**json.loads(path.read_text(encoding="utf-8")))

    def event(self, job_id: str, event: str, details: Mapping[str, Any] | None = None) -> None:
        row = {
            "ts": time.time(),
            "job_id": job_id,
            "event": event,
            "details": dict(details or {}),
        }
        with self._lock:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


class MrosAgentBridge:
    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.store = JobStore(config.state_root)
        self._semaphore = threading.BoundedSemaphore(config.max_parallel_jobs)
        self._threads: dict[str, threading.Thread] = {}
        self._thread_lock = threading.Lock()
        self._validate_repo_root()

    def _validate_repo_root(self) -> None:
        actual = self.config.repo_root.resolve()
        allowed = self.config.allowed_repo_realpath.resolve()
        if actual != allowed:
            raise BridgeError("REPOSITORY_ROOT_NOT_ALLOWLISTED")
        git_marker = actual / ".git"
        if not git_marker.exists():
            raise BridgeError("REPOSITORY_GIT_MARKER_MISSING")

    def health(self) -> dict[str, Any]:
        git_ok = shutil.which("git") is not None
        backend_status = {
            name: shutil.which(spec.argv_template[0]) is not None
            for name, spec in self.config.backends.items()
            if spec.argv_template
        }
        return {
            "status": "ok" if git_ok else "blocked",
            "git_available": git_ok,
            "repo_root": str(self.config.repo_root),
            "backends": backend_status,
            "max_parallel_jobs": self.config.max_parallel_jobs,
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
        }

    def submit(self, payload: Mapping[str, Any]) -> JobRecord:
        job_type = str(payload.get("job_type") or "").strip().lower()
        role_id = str(payload.get("role_id") or "").strip().upper()
        candidate_sha = str(payload.get("candidate_sha") or "").strip().lower()
        packet_path = str(payload.get("packet_path") or "").strip()
        output_path = str(payload.get("output_path") or "").strip()
        backend = str(payload.get("backend") or "").strip()

        if job_type not in JOB_TYPES:
            raise BridgeError("JOB_TYPE_INVALID")
        if not ROLE_RE.fullmatch(role_id):
            raise BridgeError("ROLE_ID_INVALID")
        if job_type == "reviewer" and not role_id.startswith("R"):
            raise BridgeError("ROLE_JOB_TYPE_MISMATCH")
        if job_type == "auditor" and not role_id.startswith("A"):
            raise BridgeError("ROLE_JOB_TYPE_MISMATCH")
        if not SHA40_RE.fullmatch(candidate_sha):
            raise BridgeError("CANDIDATE_SHA_INVALID")
        if backend not in self.config.backends:
            raise BridgeError("BACKEND_NOT_ALLOWLISTED")

        packet = self._resolve_repo_file(packet_path, must_exist=True)
        output = self._resolve_repo_file(output_path, must_exist=False)
        if packet == output:
            raise BridgeError("PACKET_OUTPUT_PATH_COLLISION")
        if output.exists():
            raise BridgeError("OUTPUT_PATH_ALREADY_EXISTS")

        self._assert_git_object(candidate_sha)
        job_id = uuid.uuid4().hex
        record = JobRecord(
            job_id=job_id,
            job_type=job_type,
            role_id=role_id,
            candidate_sha=candidate_sha,
            packet_path=packet_path,
            output_path=output_path,
            backend=backend,
        )
        self.store.save(record)
        self.store.event(job_id, "JOB_QUEUED", {"candidate_sha": candidate_sha, "role_id": role_id})
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        with self._thread_lock:
            self._threads[job_id] = thread
        thread.start()
        return record

    def get(self, job_id: str) -> JobRecord:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise BridgeError("JOB_ID_INVALID")
        return self.store.load(job_id)

    def _resolve_repo_file(self, relative: str, *, must_exist: bool) -> Path:
        if not relative or Path(relative).is_absolute():
            raise BridgeError("REPOSITORY_PATH_INVALID")
        candidate = (self.config.repo_root / relative).resolve()
        repo = self.config.repo_root.resolve()
        try:
            candidate.relative_to(repo)
        except ValueError as exc:
            raise BridgeError("REPOSITORY_PATH_ESCAPE") from exc
        if must_exist and not candidate.is_file():
            raise BridgeError("PACKET_PATH_NOT_FOUND")
        if not must_exist:
            candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    def _assert_git_object(self, sha: str) -> None:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=self.config.repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            raise BridgeError("CANDIDATE_SHA_NOT_PRESENT_LOCALLY")

    def _run_job(self, job_id: str) -> None:
        with self._semaphore:
            record = self.store.load(job_id)
            record.state = "RUNNING"
            record.started_at = time.time()
            self.store.save(record)
            self.store.event(job_id, "JOB_STARTED")
            worktree: Path | None = None
            try:
                worktree = self._create_worktree(record)
                record.worktree_path = str(worktree)
                spec = self.config.backends[record.backend]
                packet = self.config.repo_root / record.packet_path
                output = self.config.repo_root / record.output_path
                argv = spec.render(worktree=worktree, packet=packet, output=output)
                record.command_hash = hashlib.sha256("\0".join(argv).encode("utf-8")).hexdigest()
                self.store.save(record)
                env = self._fresh_job_env(record, worktree, output)
                completed = subprocess.run(
                    argv,
                    cwd=worktree,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=spec.timeout_seconds,
                    check=False,
                )
                log_path = self.config.state_root / "jobs" / f"{job_id}.log"
                log_path.write_text(completed.stdout or "", encoding="utf-8")
                record.exit_code = completed.returncode
                if completed.returncode != 0:
                    raise BridgeError("BACKEND_EXIT_NONZERO")
                if not output.is_file() or output.stat().st_size == 0:
                    raise BridgeError("OUTPUT_ARTIFACT_MISSING")
                record.state = "SUCCEEDED"
                self.store.event(job_id, "JOB_SUCCEEDED", {"output_path": record.output_path})
            except subprocess.TimeoutExpired as exc:
                record.state = "FAILED"
                record.error_code = "BACKEND_TIMEOUT"
                record.error_detail = str(exc)
                self.store.event(job_id, "JOB_FAILED", {"error_code": record.error_code})
            except BridgeError as exc:
                record.state = "BLOCKED" if str(exc) in {
                    "CANDIDATE_SHA_NOT_PRESENT_LOCALLY",
                    "BACKEND_NOT_ALLOWLISTED",
                } else "FAILED"
                record.error_code = str(exc)
                record.error_detail = str(exc)
                self.store.event(job_id, "JOB_FAILED", {"error_code": record.error_code})
            except Exception as exc:
                record.state = "FAILED"
                record.error_code = "UNEXPECTED_BRIDGE_ERROR"
                record.error_detail = f"{type(exc).__name__}: {exc}"
                self.store.event(job_id, "JOB_FAILED", {"error_code": record.error_code})
            finally:
                if worktree is not None:
                    self._remove_worktree(worktree)
                # Publish terminal state only after isolation cleanup completes.
                record.finished_at = time.time()
                self.store.save(record)
                with self._thread_lock:
                    self._threads.pop(job_id, None)

    def _create_worktree(self, record: JobRecord) -> Path:
        self.config.worktree_root.mkdir(parents=True, exist_ok=True)
        worktree = self.config.worktree_root / f"mros-{record.job_type}-{record.role_id}-{record.job_id[:8]}"
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), record.candidate_sha],
            cwd=self.config.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            raise BridgeError("WORKTREE_CREATE_FAILED")
        return worktree

    def _remove_worktree(self, worktree: Path) -> None:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=self.config.repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
        shutil.rmtree(worktree, ignore_errors=True)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self.config.repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )

    def _fresh_job_env(self, record: JobRecord, worktree: Path, output: Path) -> dict[str, str]:
        keep = {
            "HOME",
            "PATH",
            "LANG",
            "LC_ALL",
            "TMPDIR",
            "USER",
            "LOGNAME",
            "SHELL",
            "TERM",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
        }
        env = {key: value for key, value in os.environ.items() if key in keep}
        env.update(
            {
                "MROS_JOB_ID": record.job_id,
                "MROS_JOB_TYPE": record.job_type,
                "MROS_ROLE_ID": record.role_id,
                "MROS_CANDIDATE_SHA": record.candidate_sha,
                "MROS_OUTPUT_PATH": str(output),
                "MROS_WORKTREE": str(worktree),
                "MROS_RUNTIME_AUTHORITY": "NONE",
                "MROS_BROKER_ACTIONS_ALLOWED": "0",
            }
        )
        return env


def load_backend_specs(raw: Mapping[str, Any]) -> dict[str, BackendSpec]:
    specs: dict[str, BackendSpec] = {}
    for name, value in raw.items():
        if not isinstance(value, Mapping):
            raise BridgeError("BACKEND_SPEC_INVALID")
        argv = value.get("argv")
        if not isinstance(argv, Sequence) or isinstance(argv, (str, bytes)):
            raise BridgeError("BACKEND_ARGV_INVALID")
        parts = tuple(str(item) for item in argv)
        if not parts:
            raise BridgeError("BACKEND_ARGV_EMPTY")
        timeout = int(value.get("timeout_seconds") or 3600)
        if timeout < 30 or timeout > 14400:
            raise BridgeError("BACKEND_TIMEOUT_INVALID")
        specs[str(name)] = BackendSpec(name=str(name), argv_template=parts, timeout_seconds=timeout)
    return specs


def load_config(path: Path) -> BridgeConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    repo_root = Path(raw["repo_root"]).expanduser().resolve()
    allowed = Path(raw.get("allowed_repo_realpath") or repo_root).expanduser().resolve()
    return BridgeConfig(
        repo_root=repo_root,
        worktree_root=Path(raw["worktree_root"]).expanduser().resolve(),
        state_root=Path(raw["state_root"]).expanduser().resolve(),
        allowed_repo_realpath=allowed,
        backends=load_backend_specs(raw.get("backends") or {}),
        max_parallel_jobs=max(1, min(int(raw.get("max_parallel_jobs") or 4), 20)),
    )


__all__ = [
    "BackendSpec",
    "BridgeConfig",
    "BridgeError",
    "JobRecord",
    "JobStore",
    "MrosAgentBridge",
    "load_backend_specs",
    "load_config",
]
