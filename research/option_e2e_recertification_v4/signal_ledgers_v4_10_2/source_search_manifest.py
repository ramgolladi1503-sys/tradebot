from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

SCHEMA_VERSION = "v4_10_2_source_search_v2"
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
EXCLUDED_DIR_NAMES = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


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


def _run_git(repo_root: Path, args: Sequence[str], timeout_seconds: int = 30) -> dict[str, object]:
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
        stderr = result.stderr.strip()
        return {
            "command": command,
            "exit_code": result.returncode,
            "timed_out": False,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stdout_lines": stdout.splitlines(),
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return {
            "command": command,
            "exit_code": None,
            "timed_out": True,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stdout_lines": stdout.splitlines(),
            "stderr": "timeout",
        }


def _parse_worktree_paths(lines: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for line in lines:
        if line.startswith("worktree "):
            paths.append(Path(line.removeprefix("worktree ").strip()))
    return paths


def discover_root_inventory(
    repo_root: Path,
    external_roots: Sequence[tuple[str, Path]] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    repo_root = repo_root.resolve()
    worktree_command = _run_git(repo_root, ["worktree", "list", "--porcelain"])
    roots: list[tuple[str, Path, str]] = [("CURRENT_WORKTREE", repo_root, "CURRENT_WORKTREE")]
    roots.extend((root_id, path, "EXTERNAL_ROOT") for root_id, path in (external_roots or DEFAULT_EXTERNAL_ROOTS))

    seen = {repo_root}
    for index, path in enumerate(_parse_worktree_paths(worktree_command["stdout_lines"])):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append((f"REGISTERED_WORKTREE_{index:03d}", resolved, "REGISTERED_TRADEBOT_WORKTREE"))

    inventory = [
        {
            "root_id": root_id,
            "root_class": root_class,
            "available": path.exists(),
            "is_directory": path.is_dir(),
        }
        for root_id, path, root_class in roots
    ]
    diagnostics = {
        "root_paths": {root_id: str(path) for root_id, path, _ in roots},
        "worktree_command": worktree_command,
    }
    return inventory, diagnostics


def _sample_csv(path: Path, limit: int = 1000) -> tuple[list[str], int, list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        for index, row in enumerate(reader):
            if index >= limit:
                break
            rows.append(dict(row))
    return columns, len(rows), rows


def _sample_json(path: Path, limit: int = 1000) -> tuple[list[str], int, list[dict[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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
    sample = parquet_file.read_row_group(0).slice(0, min(1000, row_count)).to_pylist() if row_count else []
    return columns, row_count, [row for row in sample if isinstance(row, dict)]


def _archive_members(path: Path) -> list[str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return sorted(archive.namelist())
    with tarfile.open(path, "r:*") as archive:
        return sorted(member.name for member in archive.getmembers() if member.isfile())


def _looks_nifty(path_text: str, rows: list[dict[str, object]]) -> bool:
    haystack = path_text.lower()
    if "nifty" in haystack or "aeron7" in haystack:
        return True
    for row in rows[:100]:
        for key in ("symbol", "instrument", "underlying", "ticker"):
            value = str(row.get(key, "")).lower()
            if "nifty" in value:
                return True
    return False


def inspect_candidate(root_id: str, root: Path, path: Path) -> dict[str, object]:
    relative_path = path.relative_to(root).as_posix()
    lowered_parts = {part.lower() for part in path.parts}
    base = {
        "root_id": root_id,
        "relative_path": relative_path,
        "suffix": path.suffix.lower(),
        "size": path.stat().st_size,
        "sha256": file_sha256(path),
    }

    if ".git" in lowered_parts:
        return {**base, "classification": "GIT_INTERNAL", "accepted": False, "rejection_code": "GIT_INTERNAL_NOT_EVIDENCE"}
    if "tests" in lowered_parts:
        return {**base, "classification": "TEST_ONLY", "accepted": False, "rejection_code": "TEST_ONLY_NOT_EVIDENCE"}
    if "docs" in lowered_parts or path.suffix.lower() in {".md", ".rst", ".txt"}:
        return {**base, "classification": "DOCUMENTATION_ONLY", "accepted": False, "rejection_code": "DOCUMENTATION_NOT_SOURCE"}
    if path.suffix.lower() == ".py":
        classification = "STRATEGY_IMPLEMENTATION" if relative_path.endswith("strategies/movement/vwap_reclaim.py") else "SOURCE_CODE_ONLY"
        return {**base, "classification": classification, "accepted": classification == "STRATEGY_IMPLEMENTATION", "rejection_code": None if classification == "STRATEGY_IMPLEMENTATION" else "SOURCE_CODE_NOT_MARKET_DATA"}

    suffix = path.suffix.lower()
    if suffix in {".zip", ".tar", ".tgz", ".gz"}:
        try:
            members = _archive_members(path)
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            return {**base, "classification": "ARCHIVE_INVALID", "accepted": False, "unresolved": False, "rejection_code": f"ARCHIVE_READ_FAILED:{type(exc).__name__}"}
        plausible = [member for member in members if Path(member).suffix.lower() in SUPPORTED_SUFFIXES]
        return {
            **base,
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
            return {**base, "classification": "IRRELEVANT", "accepted": False, "rejection_code": "UNSUPPORTED_FILE_TYPE"}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {**base, "classification": "UNREADABLE_CANDIDATE", "accepted": False, "unresolved": False, "rejection_code": f"CONTENT_READ_FAILED:{type(exc).__name__}"}

    normalized_columns = {column.lower() for column in columns}
    has_timestamp = bool(normalized_columns & TIMESTAMP_NAMES)
    has_ohlcv = REQUIRED_OHLCV.issubset(normalized_columns)
    has_signal_schema = SIGNAL_REQUIRED_FIELDS.issubset(normalized_columns)
    nifty_identity = _looks_nifty(relative_path, rows)

    if has_signal_schema:
        return {
            **base,
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
            "classification": "UNDERLYING_CANDLE_DATASET",
            "accepted": accepted,
            "unresolved": False,
            "row_count": row_count,
            "columns": sorted(columns),
            "nifty_identity": nifty_identity,
            "rejection_code": None if accepted else "DATASET_IDENTITY_NOT_NIFTY" if row_count else "EMPTY_DATASET",
        }

    keys = normalized_columns
    if {"data_fetch_attempted", "data_fetch_status"}.issubset(keys):
        classification = "OPTION_REPLAY_REPORT"
        rejection = "OPTION_REPLAY_REPORT_NOT_SIGNAL_SOURCE"
    else:
        classification = "IRRELEVANT_STRUCTURED_ARTIFACT"
        rejection = "REQUIRED_SIGNAL_OR_OHLCV_SCHEMA_MISSING"
    return {
        **base,
        "classification": classification,
        "accepted": False,
        "unresolved": False,
        "row_count": row_count,
        "columns": sorted(columns),
        "rejection_code": rejection,
    }


def _candidate_paths(root: Path, max_candidates: int) -> tuple[list[Path], bool]:
    candidates: list[Path] = []
    truncated = False
    for path in sorted(root.rglob("*")):
        if any(part.lower() in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES and suffix not in {".py", ".md", ".txt"}:
            continue
        name = path.as_posix().lower()
        if suffix in SUPPORTED_SUFFIXES or any(term in name for term in SEARCH_TERMS):
            candidates.append(path)
        if len(candidates) >= max_candidates:
            truncated = True
            break
    return candidates, truncated


def _git_search_manifest(repo_root: Path) -> list[dict[str, object]]:
    commands = [
        ["branch", "--all"],
        ["log", "--all", "-S", "VWAP_RECLAIM", "--oneline"],
        ["log", "--all", "-S", "vwap_reclaim_rejection_v1", "--oneline"],
        ["log", "--all", "-S", "NIFTY_F1", "--oneline"],
        ["log", "--all", "-S", "Aeron7", "--oneline"],
        ["rev-list", "--all", "--", "strategies/movement/vwap_reclaim.py"],
        ["log", "--all", "--name-only", "--", "strategies/movement/vwap_reclaim.py"],
    ]
    return [_run_git(repo_root, command) for command in commands]


def _compute_verdict(
    root_inventory: list[dict[str, object]],
    git_searches: list[dict[str, object]],
    candidates: list[dict[str, object]],
    truncated: bool,
) -> tuple[str, list[str]]:
    accepted = [candidate for candidate in candidates if candidate.get("accepted")]
    if accepted:
        return SOURCE_RESOLVED, []

    reasons: list[str] = []
    if any(not root.get("available") or not root.get("is_directory") for root in root_inventory):
        reasons.append("APPROVED_ROOT_UNAVAILABLE")
    if any(search.get("exit_code") != 0 or search.get("timed_out") for search in git_searches):
        reasons.append("GIT_SEARCH_INCOMPLETE")
    if truncated:
        reasons.append("CANDIDATE_INVENTORY_TRUNCATED")
    if any(candidate.get("unresolved") for candidate in candidates):
        reasons.append("UNRESOLVED_CANDIDATE")

    aeron_search = next((search for search in git_searches if "Aeron7" in search.get("command", [])), None)
    nifty_f1_search = next((search for search in git_searches if "NIFTY_F1" in search.get("command", [])), None)
    lead_resolved = bool(
        any("aeron7" in candidate.get("relative_path", "").lower() or "nifty_f1" in candidate.get("relative_path", "").lower() for candidate in candidates)
        or (aeron_search and aeron_search.get("stdout_lines"))
        or (nifty_f1_search and nifty_f1_search.get("stdout_lines"))
    )
    if not lead_resolved:
        reasons.append("AERON7_NIFTY_F1_LEAD_UNRESOLVED")

    if reasons:
        return SOURCE_INCOMPLETE, sorted(set(reasons))
    return SOURCE_BLOCKED, ["ALL_PLAUSIBLE_CANDIDATES_REJECTED"]


def generate_source_search_evidence(
    repo_root: Path,
    *,
    external_roots: Sequence[tuple[str, Path]] | None = None,
    max_candidates_per_root: int = 10000,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    root_inventory, diagnostics = discover_root_inventory(repo_root, external_roots)
    root_paths = diagnostics["root_paths"]
    git_searches = _git_search_manifest(repo_root)
    candidates: list[dict[str, object]] = []
    truncated = False

    for root_record in root_inventory:
        if not root_record["available"] or not root_record["is_directory"]:
            continue
        root_id = str(root_record["root_id"])
        root = Path(root_paths[root_id])
        paths, root_truncated = _candidate_paths(root, max_candidates_per_root)
        truncated = truncated or root_truncated
        for path in paths:
            candidates.append(inspect_candidate(root_id, root, path))

    conclusion, reason_codes = _compute_verdict(root_inventory, git_searches, candidates, truncated)
    semantic_payload = {
        "schema_version": SCHEMA_VERSION,
        "root_inventory": root_inventory,
        "git_searches": git_searches,
        "candidate_inventory": candidates,
        "candidate_count": len(candidates),
        "accepted_candidate_count": sum(1 for candidate in candidates if candidate.get("accepted")),
        "unresolved_candidate_count": sum(1 for candidate in candidates if candidate.get("unresolved")),
        "truncated": truncated,
        "conclusion": conclusion,
        "reason_codes": reason_codes,
    }
    return {
        **semantic_payload,
        "semantic_sha256": semantic_hash(semantic_payload),
        "diagnostics": diagnostics,
    }


def build_source_search_manifest(repo_root: Path) -> dict[str, object]:
    """Return a read-only fail-closed manifest until local evidence generation runs."""
    root_inventory, diagnostics = discover_root_inventory(repo_root)
    semantic_payload = {
        "schema_version": SCHEMA_VERSION,
        "root_inventory": root_inventory,
        "git_searches": [],
        "candidate_inventory": [],
        "candidate_count": 0,
        "accepted_candidate_count": 0,
        "unresolved_candidate_count": 0,
        "truncated": False,
        "conclusion": SOURCE_INCOMPLETE,
        "reason_codes": ["SOURCE_EVIDENCE_NOT_GENERATED"],
    }
    return {
        **semantic_payload,
        "semantic_sha256": semantic_hash(semantic_payload),
        "diagnostics": diagnostics,
    }
