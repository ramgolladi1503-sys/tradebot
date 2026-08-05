#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "runtime_cleanup"
SHARED_ROOT = Path(os.getenv("TRADEBOT_DATA_ROOT", str(Path.home() / "tradebot-shared-data"))).expanduser()
TRADEBOT_GLOBS = (
    Path.home().glob("tradebot-*"),
    (Path.home() / ".codex" / "worktrees" / "tradebot").glob("*"),
    (Path.home() / ".antigravity" / "worktrees" / "tradebot").glob("*"),
)
ACTIVE_CAMPAIGN_MARKERS = (
    "meg-dual-provider-20260805-05",
    "meg-dual-provider-20260805-06",
)
ACTIVE_REPAIR_RUNTIME = Path("/Users/madhuram/tradebot-kite-depth-persistence-saturation-v1/runtime")


def run(args: list[str], cwd: Path = REPO_ROOT) -> dict[str, Any]:
    proc = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "args": args,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def du_k(path: Path) -> int | None:
    if not path.exists():
        return None
    proc = subprocess.run(["du", "-sk", str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return int(proc.stdout.split()[0])


def find_count_and_bytes(root: Path, patterns: tuple[str, ...]) -> dict[str, int]:
    count = 0
    bytes_total = 0
    if not root.exists():
        return {"count": 0, "bytes": 0}
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.is_file():
                count += 1
                try:
                    bytes_total += path.stat().st_size
                except OSError:
                    pass
    return {"count": count, "bytes": bytes_total}


def large_files(root: Path, limit: int = 100) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size >= 50 * 1024 * 1024:
            rows.append({"path": str(path), "bytes": size})
    return sorted(rows, key=lambda row: row["bytes"], reverse=True)[:limit]


def parse_worktrees() -> list[dict[str, Any]]:
    output = run(["git", "worktree", "list", "--porcelain"])["stdout"]
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in output.splitlines():
        if not line:
            if current:
                rows.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value
        elif key == "detached":
            current["detached"] = True
    if current:
        rows.append(current)
    return rows


def process_references(path: Path) -> str:
    ps = run(["ps", "aux"])["stdout"]
    return "\n".join(line for line in ps.splitlines() if str(path) in line)


def worktree_inventory() -> list[dict[str, Any]]:
    registered = {Path(row["path"]).resolve(): row for row in parse_worktrees()}
    candidates = set(registered)
    for glob_iter in TRADEBOT_GLOBS:
        for path in glob_iter:
            if path.is_dir():
                candidates.add(path.resolve())

    rows: list[dict[str, Any]] = []
    for path in sorted(candidates):
        runtime = path / "runtime"
        dot_runtime = path / ".runtime"
        status = run(["git", "status", "--short", "--branch"], cwd=path) if (path / ".git").exists() else None
        row = {
            "path": str(path),
            "registered_worktree": path in registered,
            "branch": registered.get(path, {}).get("branch"),
            "head": registered.get(path, {}).get("head"),
            "git_status": status,
            "active_process_references": process_references(path),
            "runtime_kib": du_k(runtime),
            "dot_runtime_kib": du_k(dot_runtime),
            "large_files_over_50m": large_files(runtime) + large_files(dot_runtime),
            "parquet": find_count_and_bytes(runtime, ("*.parquet",)),
            "dot_runtime_parquet": find_count_and_bytes(dot_runtime, ("*.parquet",)),
            "live_evidence": find_count_and_bytes(runtime / "live_evidence", ("*",)),
            "historical_or_replay": find_count_and_bytes(runtime, ("*.parquet", "*.jsonl", "*.zip")),
            "contains_active_campaign_marker": any(
                marker in str(p)
                for marker in ACTIVE_CAMPAIGN_MARKERS
                for p in list(runtime.rglob(f"*{marker}*"))[:1]
            )
            if runtime.exists()
            else False,
        }
        rows.append(row)
    return rows


def classify_runtime_path(path: str) -> str:
    lowered = path.lower()
    if "kite_access_token" in lowered or ".env" in lowered:
        return "SECRET_OR_TOKEN"
    if path.endswith((".py", ".sh")):
        return "SOURCE_CODE"
    if path.endswith((".schema.json", ".yaml", ".yml", ".toml")):
        return "SCHEMA"
    if "fixture" in lowered:
        return "SMALL_TEST_FIXTURE"
    if any(part in lowered for part in ("market_data", "historical", "instruments")) and path.endswith((".parquet", ".json", ".json.gz")):
        return "HISTORICAL_DATA"
    if "replay" in lowered:
        return "REPLAY_DATA"
    if any(part in lowered for part in ("live_evidence", "live_observation", "feed_soak", "diagnostic")):
        return "GENERATED_EVIDENCE"
    if any(part in lowered for part in ("cache", ".ds_store", "__pycache__")):
        return "CACHE"
    if path.startswith("runtime/"):
        return "GENERATED_EVIDENCE"
    return "UNKNOWN"


def tracked_runtime_classification() -> list[dict[str, Any]]:
    lfs_paths = {line.split()[-1] for line in run(["git", "lfs", "ls-files"])["stdout"].splitlines() if line.strip()}
    files = [
        line.strip()
        for line in (run(["git", "ls-files", "runtime"])["stdout"] + "\n" + run(["git", "ls-files", ".runtime"])["stdout"]).splitlines()
        if line.strip()
    ]
    latest_commits: dict[str, str] = {}
    log_output = run(["git", "log", "--name-only", "--format=commit %H", "--", "runtime", ".runtime"])["stdout"]
    current_commit: str | None = None
    for line in log_output.splitlines():
        if line.startswith("commit "):
            current_commit = line.split(" ", 1)[1]
            continue
        rel = line.strip()
        if current_commit and rel and rel not in latest_commits:
            latest_commits[rel] = current_commit
    rows = []
    for rel in sorted(set(files)):
        abs_path = REPO_ROOT / rel
        rows.append(
            {
                "path": rel,
                "git_tracked": True,
                "git_lfs_tracked": rel in lfs_paths,
                "size_bytes": abs_path.stat().st_size if abs_path.exists() else None,
                "file_type": abs_path.suffix.lstrip(".") or "unknown",
                "last_commit": latest_commits.get(rel),
                "used_by_runtime_code": "UNKNOWN_REQUIRES_SOURCE_REVIEW",
                "classification": classify_runtime_path(rel),
            }
        )
    return rows


def dependency_map() -> dict[str, Any]:
    search = run(
        [
            "rg",
            "-n",
            "runtime/|\\.runtime/|historical|parquet|replay|market_data|live_evidence",
            "core",
            "scripts",
            "tests",
            "config",
            "configs",
            "docs",
            "main.py",
            "run_live.sh",
        ]
    )
    return {
        "minimal_live_runtime_requirements": [
            "DATA_ROOT runtime state directory, default .runtime",
            "Kite/Upstox credential environment and token paths; token values are not inventoried or printed",
            "writable logs, reports, locks, and db roots",
            "launch-plan or capture command inputs required by the selected live command",
        ],
        "optional_historical_research_data": [
            "TRADEBOT_HISTORICAL_DATA_ROOT for historical candles/corpora",
            "TRADEBOT_REPLAY_DATA_ROOT for replay corpora",
            "TRADEBOT_MARKET_DATA_ROOT for broker market-data captures",
            "TRADEBOT_RESEARCH_INPUTS_ROOT for research campaign inputs",
            "TRADEBOT_ARCHIVED_LIVE_EVIDENCE_ROOT for inactive evidence archives",
        ],
        "source_search": search,
    }


def write_json_and_md(name: str, payload: Any, md: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{name}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_DIR / f"{name}.md").write_text(md, encoding="utf-8")


def main() -> int:
    baseline = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(REPO_ROOT),
        "shared_root": str(SHARED_ROOT),
        "date": run(["date"]),
        "df_h": run(["df", "-h", "/"]),
        "df_k": run(["df", "-k", "/"]),
        "active_processes": run(["bash", "-lc", "ps aux | grep -E 'tradebot|kite|upstox|market_event|persistence|parquet' | grep -v grep || true"]),
        "active_repair_runtime_lsof": run(["bash", "-lc", f"lsof +D {ACTIVE_REPAIR_RUNTIME} 2>/dev/null || true"]),
    }
    write_json_and_md("disk_baseline", baseline, "# Disk Baseline\n\n```json\n" + json.dumps(baseline, indent=2) + "\n```\n")

    worktrees = worktree_inventory()
    write_json_and_md("worktree_runtime_inventory", worktrees, "# Worktree Runtime Inventory\n\n```json\n" + json.dumps(worktrees, indent=2) + "\n```\n")

    tracked = tracked_runtime_classification()
    write_json_and_md("tracked_runtime_classification", tracked, "# Tracked Runtime Classification\n\n```json\n" + json.dumps(tracked, indent=2) + "\n```\n")

    deps = dependency_map()
    write_json_and_md("runtime_path_dependency_map", deps, "# Runtime Path Dependency Map\n\n```json\n" + json.dumps(deps, indent=2) + "\n```\n")

    SHARED_ROOT.mkdir(parents=True, exist_ok=True)
    for child in ("historical", "replay", "market_data", "research_inputs", "archived_live_evidence"):
        (SHARED_ROOT / child).mkdir(exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(SHARED_ROOT),
        "status": "initialized_only_no_data_moved",
        "deletion_performed": False,
    }
    (SHARED_ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (SHARED_ROOT / "SHA256SUMS").touch(exist_ok=True)
    (SHARED_ROOT / "README.md").write_text(
        "# TradeBot Shared Data\n\n"
        "Local-only root for historical market data, replay corpora, broker captures, research inputs, and archived live evidence.\n"
        "This directory is outside Git worktrees by design.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
