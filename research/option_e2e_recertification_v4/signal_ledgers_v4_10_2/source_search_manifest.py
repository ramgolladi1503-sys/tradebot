from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Iterable, Iterator, Sequence

SCHEMA_VERSION = "v4_10_2_source_search_v3"
SOURCE_RESOLVED = "SIGNAL_SOURCE_RESOLVED"
SOURCE_BLOCKED = "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE"
SOURCE_INCOMPLETE = "SIGNAL_SOURCE_SEARCH_INCOMPLETE"

DEFAULT_EXTERNAL_ROOTS = (
    ("MAIN_TRADEBOT", Path("/Users/madhuram/tradebot")),
    ("TRADEBOT_DATA", Path("/Users/madhuram/tradebot-data")),
    ("TRADEBOT_ML_EVIDENCE", Path("/Users/madhuram/tradebot-ml-evidence")),
)

SUPPORTED_SUFFIXES = {".parquet", ".csv", ".json", ".jsonl", ".zip", ".tar", ".tgz", ".gz"}
REQUIRED_OHLCV = {"open", "high", "low", "close", "volume"}
TIMESTAMP_NAMES = {"timestamp", "datetime", "date", "bar_start_timestamp", "bar_end_timestamp"}
SIGNAL_REQUIRED_FIELDS = {
    "strategy_or_hypothesis_id",
    "signal_id",
    "signal_ts",
    "earliest_entry_ts",
    "direction",
}
SEARCH_TERMS = (
    "vwap_reclaim",
    "vwap_reclaim_rejection_v1",
    "nifty_f1",
    "aeron7",
    "completed_bar_history",
    "candidate",
    "signal",
    "session_manifest",
    "development",
    "holdout",
    "pre_outcome",
)
EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "build",
}


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semantic_hash(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(repo_root: Path, args: Sequence[str], timeout_seconds: int = 30) -> dict[str, object]:
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        stdout = result.stdout.strip()
        return {
            "command": command,
            "exit_code": result.returncode,
            "timed_out": False,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stdout_lines": stdout.splitlines(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        return {
            "command": command,
            "exit_code": None,
            "timed_out": True,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stdout_lines": stdout.splitlines(),
            "stderr": "timeout",
        }


def _parse_worktree_paths(lines: Iterable[str]) -> list[Path]:
    return [
        Path(line.removeprefix("worktree ").strip())
        for line in lines
        if line.startswith("worktree ")
    ]


def discover_root_inventory(
    repo_root: Path,
    external_roots: Sequence[tuple[str, Path]] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    repo_root = repo_root.resolve()
    worktree_command = run_git(repo_root, ["worktree", "list", "--porcelain"])
    raw_roots: list[tuple[str, Path, str]] = [("CURRENT_WORKTREE", repo_root, "CURRENT_WORKTREE")]
    raw_roots.extend((root_id, path, "EXTERNAL_ROOT") for root_id, path in (external_roots or DEFAULT_EXTERNAL_ROOTS))
    for index, path in enumerate(_parse_worktree_paths(worktree_command["stdout_lines"])):
        raw_roots.append((f"REGISTERED_WORKTREE_{index:03d}", path, "REGISTERED_TRADEBOT_WORKTREE"))

    deduped: list[tuple[str, Path, str]] = []
    seen: set[Path] = set()
    for root_id, path, root_class in raw_roots:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append((root_id, resolved, root_class))

    inventory = [
        {
            "root_id": root_id,
            "root_class": root_class,
            "available": path.exists(),
            "is_directory": path.is_dir(),
        }
        for root_id, path, root_class in deduped
    ]
    diagnostics = {
        "root_paths": {root_id: str(path) for root_id, path, _ in deduped},
        "worktree_command": worktree_command,
    }
    return inventory, diagnostics


def build_git_search_manifest(repo_root: Path) -> list[dict[str, object]]:
    commands = [
        ["branch", "--all"],
        ["log", "--all", "-S", "VWAP_RECLAIM", "--oneline"],
        ["log", "--all", "-S", "vwap_reclaim_rejection_v1", "--oneline"],
        ["log", "--all", "-S", "NIFTY_F1", "--oneline"],
        ["log", "--all", "-S", "Aeron7", "--oneline"],
        ["rev-list", "--all", "--", "strategies/movement/vwap_reclaim.py"],
        ["log", "--all", "--name-only", "--", "strategies/movement/vwap_reclaim.py"],
    ]
    return [run_git(repo_root, command) for command in commands]


def _sample_csv(path: Path, limit: int = 1000) -> tuple[list[str], int, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        for index, row in enumerate(reader):
            if index >= limit:
                break
            rows.append(dict(row))
    return columns, len(rows), rows


def _sample_json(path: Path, limit: int = 1000) -> tuple[list[str], int, list[dict[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if isinstance(payload, list):
        rows = [row for row in payload[:limit] if isinstance(row, dict)]
    elif isinstance(payload, dict):
        candidate_rows = payload.get("records") or payload.get("rows") or payload.get("signals") or []
        rows = [row for row in candidate_rows[:limit] if isinstance(row, dict)] if isinstance(candidate_rows, list) else []
        if not rows:
            rows = [payload]
    else:
        rows = []
    columns = sorted({str(key) for row in rows for key in row})
    return columns, len(rows), rows


def _sample_jsonl(path: Path, limit: int = 1000) -> tuple[list[str], int, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if len(rows) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    columns = sorted({str(key) for row in rows for key in row})
    return columns, len(rows), rows


def _sample_parquet(path: Path) -> tuple[list[str], int, list[dict[str, object]]]:
    try:
        import pyarrow.parquet as parquet  # type: ignore
    except ImportError:
        return [], 0, []
    parquet_file = parquet.ParquetFile(path)
    columns = list(parquet_file.schema_arrow.names)
    row_count = int(parquet_file.metadata.num_rows)
    rows = parquet_file.read_row_group(0).slice(0, min(1000, row_count)).to_pylist() if row_count else []
    return columns, row_count, [row for row in rows if isinstance(row, dict)]


def _archive_members(path: Path) -> list[str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return sorted(archive.namelist())
    with tarfile.open(path, "r:*") as archive:
        return sorted(member.name for member in archive.getmembers() if member.isfile())


def _looks_nifty(path_text: str, rows: list[dict[str, object]]) -> bool:
    lowered = path_text.lower()
    if "nifty" in lowered or "aeron7" in lowered:
        return True
    for row in rows[:100]:
        for key in ("symbol", "instrument", "underlying", "ticker"):
            if "nifty" in str(row.get(key, "")).lower():
                return True
    return False


def inspect_candidate(root_id: str, root: Path, path: Path, *, max_hash_bytes: int = 2 * 1024**3) -> dict[str, object]:
    relative_path = path.relative_to(root).as_posix()
    suffix = path.suffix.lower()
    size = path.stat().st_size
    base: dict[str, object] = {
        "root_id": root_id,
        "relative_path": relative_path,
        "suffix": suffix,
        "size": size,
    }

    if size > max_hash_bytes:
        return {
            **base,
            "classification": "OVERSIZED_CANDIDATE",
            "accepted": False,
            "unresolved": True,
            "rejection_code": "FILE_EXCEEDS_HASH_LIMIT",
        }

    if suffix == ".py":
        is_strategy = relative_path.endswith("strategies/movement/vwap_reclaim.py")
        return {
            **base,
            "sha256": file_sha256(path),
            "classification": "STRATEGY_IMPLEMENTATION" if is_strategy else "SOURCE_CODE_ONLY",
            "accepted": False,
            "unresolved": False,
            "rejection_code": None if is_strategy else "SOURCE_CODE_NOT_SIGNAL_SOURCE",
        }

    if suffix in {".zip", ".tar", ".tgz", ".gz"}:
        try:
            members = _archive_members(path)
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            return {
                **base,
                "sha256": file_sha256(path),
                "classification": "ARCHIVE_INVALID",
                "accepted": False,
                "unresolved": False,
                "rejection_code": f"ARCHIVE_READ_FAILED:{type(exc).__name__}",
            }
        plausible = [member for member in members if Path(member).suffix.lower() in SUPPORTED_SUFFIXES]
        return {
            **base,
            "sha256": file_sha256(path),
            "classification": "ARCHIVE_MEMBER_INVENTORY",
            "accepted": False,
            "unresolved": bool(plausible),
            "archive_member_count": len(members),
            "plausible_member_count": len(plausible),
            "rejection_code": "ARCHIVE_MEMBERS_REQUIRE_CONTENT_INSPECTION" if plausible else "ARCHIVE_NO_PLAUSIBLE_MEMBERS",
        }

    try:
        if suffix == ".csv":
            columns, row_count, rows = _sample_csv(path)
        elif suffix == ".json":
            columns, row_count, rows = _sample_json(path)
        elif suffix == ".jsonl":
            columns, row_count, rows = _sample_jsonl(path)
        elif suffix == ".parquet":
            columns, row_count, rows = _sample_parquet(path)
        else:
            return {**base, "classification": "IRRELEVANT", "accepted": False, "unresolved": False, "rejection_code": "UNSUPPORTED_FILE_TYPE"}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            **base,
            "classification": "UNREADABLE_CANDIDATE",
            "accepted": False,
            "unresolved": False,
            "rejection_code": f"CONTENT_READ_FAILED:{type(exc).__name__}",
        }

    normalized = {column.lower() for column in columns}
    has_timestamp = bool(normalized & TIMESTAMP_NAMES)
    has_ohlcv = REQUIRED_OHLCV.issubset(normalized)
    has_signal_schema = SIGNAL_REQUIRED_FIELDS.issubset(normalized)
    nifty_identity = _looks_nifty(relative_path, rows)
    digest = file_sha256(path)

    if has_signal_schema:
        return {
            **base,
            "sha256": digest,
            "classification": "PRE_OUTCOME_SIGNAL_LEDGER",
            "accepted": row_count > 0,
            "unresolved": False,
            "row_count": row_count,
            "columns": sorted(columns),
            "rejection_code": None if row_count > 0 else "EMPTY_SIGNAL_LEDGER",
        }
    if has_ohlcv and has_timestamp:
        accepted = row_count > 0 and nifty_identity
        return {
            **base,
            "sha256": digest,
            "classification": "UNDERLYING_CANDLE_DATASET",
            "accepted": accepted,
            "unresolved": False,
            "row_count": row_count,
            "columns": sorted(columns),
            "nifty_identity": nifty_identity,
            "rejection_code": None if accepted else "DATASET_IDENTITY_NOT_NIFTY" if row_count else "EMPTY_DATASET",
        }

    classification = "OPTION_REPLAY_REPORT" if {"data_fetch_attempted", "data_fetch_status"}.issubset(normalized) else "IRRELEVANT_STRUCTURED_ARTIFACT"
    rejection = "OPTION_REPLAY_REPORT_NOT_SIGNAL_SOURCE" if classification == "OPTION_REPLAY_REPORT" else "REQUIRED_SIGNAL_OR_OHLCV_SCHEMA_MISSING"
    return {
        **base,
        "sha256": digest,
        "classification": classification,
        "accepted": False,
        "unresolved": False,
        "row_count": row_count,
        "columns": sorted(columns),
        "rejection_code": rejection,
    }


def iter_candidate_paths(
    root: Path,
    root_class: str,
    *,
    max_candidates: int,
    max_seconds: int,
    excluded_paths: Sequence[Path] = (),
) -> Iterator[Path]:
    started = time.monotonic()
    yielded = 0
    excluded = [path.resolve() for path in excluded_paths]

    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        dirnames[:] = [
            name
            for name in sorted(dirnames)
            if name.lower() not in EXCLUDED_DIR_NAMES
            and not any((current_path / name).resolve() == blocked or blocked in (current_path / name).resolve().parents for blocked in excluded)
        ]
        for filename in sorted(filenames):
            if time.monotonic() - started > max_seconds:
                return
            path = current_path / filename
            suffix = path.suffix.lower()
            relative = path.relative_to(root).as_posix().lower()
            exact_strategy = relative.endswith("strategies/movement/vwap_reclaim.py")
            external_data = root_class == "EXTERNAL_ROOT" and suffix in SUPPORTED_SUFFIXES
            term_match = any(term in relative for term in SEARCH_TERMS)
            if not exact_strategy and not external_data and not (suffix in SUPPORTED_SUFFIXES and term_match):
                continue
            yield path
            yielded += 1
            if yielded >= max_candidates:
                return


def compute_source_verdict(
    *,
    root_inventory: list[dict[str, object]],
    git_searches: list[dict[str, object]],
    accepted_candidate_count: int,
    unresolved_candidate_count: int,
    truncated: bool,
    timed_out_root_count: int,
    aeron7_nifty_f1_resolved: bool,
) -> tuple[str, list[str]]:
    if accepted_candidate_count > 0:
        return SOURCE_RESOLVED, []

    reasons: list[str] = []
    if any(not root.get("available") or not root.get("is_directory") for root in root_inventory):
        reasons.append("APPROVED_ROOT_UNAVAILABLE")
    if any(search.get("exit_code") != 0 or search.get("timed_out") for search in git_searches):
        reasons.append("GIT_SEARCH_INCOMPLETE")
    if truncated:
        reasons.append("CANDIDATE_INVENTORY_TRUNCATED")
    if timed_out_root_count:
        reasons.append("ROOT_SCAN_TIMED_OUT")
    if unresolved_candidate_count:
        reasons.append("UNRESOLVED_CANDIDATE")
    if not aeron7_nifty_f1_resolved:
        reasons.append("AERON7_NIFTY_F1_LEAD_UNRESOLVED")

    if reasons:
        return SOURCE_INCOMPLETE, sorted(set(reasons))
    return SOURCE_BLOCKED, ["ALL_PLAUSIBLE_CANDIDATES_REJECTED"]


def build_source_search_manifest(repo_root: Path) -> dict[str, object]:
    """Return a read-only fail-closed manifest until local evidence generation runs."""
    root_inventory, diagnostics = discover_root_inventory(repo_root)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "root_inventory": root_inventory,
        "git_searches": [],
        "candidate_count": 0,
        "accepted_candidate_count": 0,
        "unresolved_candidate_count": 0,
        "truncated": False,
        "conclusion": SOURCE_INCOMPLETE,
        "reason_codes": ["SOURCE_EVIDENCE_NOT_GENERATED"],
    }
    return {**payload, "semantic_sha256": semantic_hash(payload), "diagnostics": diagnostics}
