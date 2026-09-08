from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FREEZE_NAMES = (
    "MACD_CANONICAL_REIMPLEMENTATION_FREEZE.json",
    "MACD_CANONICAL_IMPLEMENTATION_SPEC.json",
)
LATENCY_HINTS = ("latency", "delay", "robust", "timing")


class CanonicalAuthorityBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthorityResolution:
    evidence_root: str
    evidence_files: dict[str, str]
    implementation_candidates: list[dict[str, Any]]
    verified_implementation_candidates: list[dict[str, Any]]
    latency_artifacts: list[str]
    status: str
    blocker: str | None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise CanonicalAuthorityBlocked(
            f"INVALID_JSON:{path}:{type(exc).__name__}"
        ) from exc


def _walk(obj: Any, prefix: tuple[str, ...] = ()):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk(value, prefix + (str(key),))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _walk(value, prefix + (str(index),))
    else:
        yield prefix, obj


def _looks_like_implementation_key(key_path: tuple[str, ...]) -> bool:
    joined = ".".join(key_path).lower()
    pathish = any(
        token in joined
        for token in ("path", "file", "script", "implementation", "source")
    )
    strategyish = any(
        token in joined
        for token in ("implementation", "macd", "canonical", "script", "source")
    )
    return pathish and strategyish


def _extract_candidates(obj: Any, source_json: Path) -> list[dict[str, Any]]:
    leaves = list(_walk(obj))
    candidates: list[dict[str, Any]] = []
    sha_leaves = [
        (path, str(value).lower())
        for path, value in leaves
        if isinstance(value, str) and len(str(value)) == 64
    ]
    for key_path, value in leaves:
        if not isinstance(value, str) or not _looks_like_implementation_key(key_path):
            continue
        text = value.strip()
        if not text or not (text.endswith(".py") or "/" in text):
            continue
        expected_sha = None
        parent = key_path[:-1]
        for sha_path, sha_value in sha_leaves:
            if sha_path[:-1] == parent and "sha" in sha_path[-1].lower():
                expected_sha = sha_value
                break
        candidates.append(
            {
                "declared_in": str(source_json),
                "key": ".".join(key_path),
                "path": text,
                "expected_sha256": expected_sha,
            }
        )

    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for candidate in candidates:
        key = (candidate["path"], candidate["expected_sha256"])
        if key not in seen:
            output.append(candidate)
            seen.add(key)
    return output


def _resolve_path(
    text: str,
    evidence_root: Path,
    repo_root: Path | None,
) -> Path | None:
    path = Path(text).expanduser()
    probes = [path]
    if not path.is_absolute():
        probes.append(evidence_root / path)
        if repo_root is not None:
            probes.append(repo_root / path)
    for probe in probes:
        if probe.exists() and probe.is_file():
            return probe.resolve()
    return None


def resolve_canonical_authority(
    evidence_root: Path,
    repo_root: Path | None = None,
) -> AuthorityResolution:
    evidence_root = evidence_root.expanduser().resolve()
    if not evidence_root.is_dir():
        raise CanonicalAuthorityBlocked(f"MISSING_EVIDENCE_ROOT:{evidence_root}")

    evidence_files: dict[str, str] = {}
    implementation_candidates: list[dict[str, Any]] = []
    for name in FREEZE_NAMES:
        path = evidence_root / name
        if not path.is_file():
            raise CanonicalAuthorityBlocked(f"MISSING_REQUIRED_AUTHORITY:{path}")
        evidence_files[name] = sha256_file(path)
        implementation_candidates.extend(_extract_candidates(_load_json(path), path))

    verified: list[dict[str, Any]] = []
    for candidate in implementation_candidates:
        resolved = _resolve_path(candidate["path"], evidence_root, repo_root)
        row = dict(candidate)
        row["resolved_path"] = str(resolved) if resolved else None
        row["actual_sha256"] = sha256_file(resolved) if resolved else None
        row["sha_match"] = (
            True
            if resolved and not candidate["expected_sha256"]
            else bool(
                resolved
                and candidate["expected_sha256"]
                and row["actual_sha256"] == candidate["expected_sha256"]
            )
        )
        if resolved and row["sha_match"]:
            verified.append(row)

    latency_artifacts = sorted(
        str(path)
        for path in evidence_root.iterdir()
        if path.is_file()
        and any(hint in path.name.lower() for hint in LATENCY_HINTS)
    )

    if verified:
        status, blocker = "PASS", None
    elif implementation_candidates:
        status = "BLOCKED"
        blocker = "DECLARED_IMPLEMENTATION_NOT_PRESENT_OR_SHA_MISMATCH"
    else:
        status = "BLOCKED"
        blocker = "NO_IMPLEMENTATION_PATH_DECLARED_IN_FREEZE_OR_SPEC"

    return AuthorityResolution(
        evidence_root=str(evidence_root),
        evidence_files=evidence_files,
        implementation_candidates=implementation_candidates,
        verified_implementation_candidates=verified,
        latency_artifacts=latency_artifacts,
        status=status,
        blocker=blocker,
    )


def as_dict(resolution: AuthorityResolution) -> dict[str, Any]:
    return {
        "evidence_root": resolution.evidence_root,
        "evidence_files": resolution.evidence_files,
        "implementation_candidates": resolution.implementation_candidates,
        "verified_implementation_candidates": resolution.verified_implementation_candidates,
        "latency_artifacts": resolution.latency_artifacts,
        "status": resolution.status,
        "blocker": resolution.blocker,
        "structural_edge_certified": False,
        "broker_write_authority": False,
        "order_authority": False,
    }
