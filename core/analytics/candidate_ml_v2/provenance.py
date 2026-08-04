from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION


@dataclass(frozen=True)
class SourceFileEvidence:
    role: str
    path: str
    sha256: str
    bytes: int
    records: int
    file_format: str
    regular_file: bool
    symlink: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_json_records(path: Path) -> int:
    if path.suffix.lower() == ".jsonl":
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError(f"source_non_object_jsonl_row:{path}:{line_number}")
                count += 1
        return count
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return sum(1 for item in payload if isinstance(item, dict))
    if isinstance(payload, dict):
        for key in ("events", "outcomes", "rows", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return sum(1 for item in value if isinstance(item, dict))
    raise ValueError(f"source_json_record_container_missing:{path}")


def inspect_source_file(
    path: str | Path,
    *,
    role: str,
    allowed_root: str | Path | None = None,
) -> SourceFileEvidence:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    if source.is_symlink():
        raise ValueError(f"source_symlink_rejected:{source}")
    if not source.is_file():
        raise ValueError(f"source_not_regular_file:{source}")
    resolved = source.resolve()
    if allowed_root is not None:
        root = Path(allowed_root).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"source_path_escape:{source}:{root}") from exc
    suffix = source.suffix.lower()
    if suffix not in {".json", ".jsonl"}:
        raise ValueError(f"unsupported_source_format:{source}")
    return SourceFileEvidence(
        role=str(role),
        path=str(resolved),
        sha256=_sha256(resolved),
        bytes=int(resolved.stat().st_size),
        records=_count_json_records(resolved),
        file_format=suffix.lstrip("."),
        regular_file=True,
        symlink=False,
    )


def build_input_manifest(
    sources: Mapping[str, str | Path],
    *,
    allowed_root: str | Path | None = None,
    code_sha: str = "",
) -> dict[str, Any]:
    if set(sources) != {"events", "outcomes"}:
        raise ValueError("input_manifest_requires_events_and_outcomes")
    evidence = {
        role: inspect_source_file(path, role=role, allowed_root=allowed_root).to_dict()
        for role, path in sorted(sources.items())
    }
    semantic_payload = json.dumps(
        {role: {key: value for key, value in item.items() if key != "path"} for role, item in evidence.items()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "code_sha": str(code_sha or ""),
        "sources": evidence,
        "source_contract_sha256": hashlib.sha256(semantic_payload.encode("utf-8")).hexdigest(),
        "verified": True,
        **SAFETY_CONTRACT,
    }


def verify_input_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("input_manifest_schema_mismatch")
    if manifest.get("verified") is not True:
        raise ValueError("input_manifest_not_verified")
    if manifest.get("allowed_for_live_execution") is not False:
        raise ValueError("input_manifest_unsafe_live_authority")
    sources = manifest.get("sources")
    if not isinstance(sources, dict) or set(sources) != {"events", "outcomes"}:
        raise ValueError("input_manifest_sources_invalid")
    for role, item in sources.items():
        if not isinstance(item, dict):
            raise ValueError(f"input_manifest_source_invalid:{role}")
        current = inspect_source_file(item.get("path", ""), role=role)
        if current.sha256 != item.get("sha256"):
            raise ValueError(f"input_manifest_sha_mismatch:{role}")
        if current.bytes != item.get("bytes") or current.records != item.get("records"):
            raise ValueError(f"input_manifest_size_or_count_mismatch:{role}")
