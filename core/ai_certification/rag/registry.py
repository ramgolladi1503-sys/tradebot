from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .contracts import (
    CorpusSourceRecord,
    CorpusSourceSpec,
    RAGContractError,
    source_spec_from_dict,
)


REGISTRY_SCHEMA_VERSION = "1.0"
_DEFAULT_REGISTRY_PATH = "docs/ai_certification/rag/corpus_registry_v1.json"
_ALLOWED_SOURCE_ROOTS = (
    "docs/ai_certification/",
    "docs/research/",
    "docs/agent_reviews/",
)


@dataclass(frozen=True)
class CorpusRegistry:
    records: tuple[CorpusSourceRecord, ...]
    schema_version: str = REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REGISTRY_SCHEMA_VERSION:
            raise RAGContractError(
                f"unsupported corpus registry schema: {self.schema_version!r}"
            )
        identifiers = [record.source_id for record in self.records]
        if identifiers != sorted(identifiers):
            raise RAGContractError("corpus records must be sorted by source_id")
        if len(identifiers) != len(set(identifiers)):
            raise RAGContractError("corpus source identifiers must be unique")
        paths = [record.path for record in self.records]
        if len(paths) != len(set(paths)):
            raise RAGContractError("corpus source paths must be unique")
        _validate_supersession(self.records)

    def get(self, source_id: str) -> CorpusSourceRecord:
        for record in self.records:
            if record.source_id == source_id:
                return record
        raise KeyError(f"unknown corpus source: {source_id}")

    def effective_records(self, on_date: date) -> tuple[CorpusSourceRecord, ...]:
        return tuple(
            record for record in self.records if record.is_effective(on_date)
        )

    def authority_ordered(
        self,
        *,
        on_date: date | None = None,
    ) -> tuple[CorpusSourceRecord, ...]:
        records = self.records if on_date is None else self.effective_records(on_date)
        return tuple(
            sorted(
                records,
                key=lambda record: (
                    -record.authority_rank,
                    record.source_id,
                ),
            )
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_count": sum(1 for _ in self.records),
            "records": [record.to_dict() for record in self.records],
        }

    def digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.manifest())).hexdigest()


def load_registry_specs(
    repository_root: str | Path,
    *,
    registry_path: str = _DEFAULT_REGISTRY_PATH,
) -> tuple[CorpusSourceSpec, ...]:
    root = Path(repository_root).expanduser().resolve()
    path = _resolve_under_root(root, registry_path)
    if not path.is_file():
        raise RAGContractError(f"corpus registry file not found: {registry_path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RAGContractError(f"cannot read corpus registry: {exc}") from exc
    if not isinstance(payload, dict):
        raise RAGContractError("corpus registry must be a JSON object")
    if str(payload.get("schema_version") or "") != REGISTRY_SCHEMA_VERSION:
        raise RAGContractError("corpus registry schema_version must be 1.0")
    rows = payload.get("sources")
    if not isinstance(rows, list) or not rows:
        raise RAGContractError("corpus registry requires non-empty sources")
    specs = tuple(
        sorted(
            (source_spec_from_dict(row) for row in rows if isinstance(row, dict)),
            key=lambda spec: spec.source_id,
        )
    )
    if sum(1 for row in rows if isinstance(row, dict)) != len(rows):
        raise RAGContractError("every corpus source entry must be an object")
    identifiers = [spec.source_id for spec in specs]
    if len(identifiers) != len(set(identifiers)):
        raise RAGContractError("corpus source identifiers must be unique")
    paths = [spec.path for spec in specs]
    if len(paths) != len(set(paths)):
        raise RAGContractError("corpus source paths must be unique")
    _validate_specs_supersession(specs)
    return specs


def build_registry(
    repository_root: str | Path,
    *,
    repository_commit: str,
    specs: Iterable[CorpusSourceSpec] | None = None,
) -> CorpusRegistry:
    root = Path(repository_root).expanduser().resolve()
    selected = (
        tuple(specs)
        if specs is not None
        else load_registry_specs(root)
    )
    records: list[CorpusSourceRecord] = []
    for spec in selected:
        if not any(spec.path.startswith(prefix) for prefix in _ALLOWED_SOURCE_ROOTS):
            raise RAGContractError(
                f"source {spec.source_id} is outside allowlisted corpus roots"
            )
        path = _resolve_under_root(root, spec.path)
        if not path.is_file():
            raise RAGContractError(
                f"source {spec.source_id} file not found: {spec.path}"
            )
        content = path.read_bytes()
        records.append(
            CorpusSourceRecord(
                spec=spec,
                repository_commit=repository_commit,
                content_sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            )
        )
    return CorpusRegistry(tuple(sorted(records, key=lambda row: row.source_id)))


def write_manifest(registry: CorpusRegistry, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_canonical_json(registry.manifest()) + b"\n")
    return target


def _validate_specs_supersession(specs: tuple[CorpusSourceSpec, ...]) -> None:
    identifiers = {spec.source_id for spec in specs}
    for spec in specs:
        if spec.superseded_by is not None and spec.superseded_by not in identifiers:
            raise RAGContractError(
                f"source {spec.source_id} references unknown successor "
                f"{spec.superseded_by}"
            )
    _assert_no_cycles(
        {spec.source_id: spec.superseded_by for spec in specs}
    )


def _validate_supersession(records: tuple[CorpusSourceRecord, ...]) -> None:
    identifiers = {record.source_id for record in records}
    links = {
        record.source_id: record.spec.superseded_by for record in records
    }
    for source_id, successor in links.items():
        if successor is not None and successor not in identifiers:
            raise RAGContractError(
                f"source {source_id} references unknown successor {successor}"
            )
    _assert_no_cycles(links)


def _assert_no_cycles(links: dict[str, str | None]) -> None:
    for start in links:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                raise RAGContractError(
                    f"corpus supersession cycle detected at {current}"
                )
            seen.add(current)
            current = links.get(current)


def _resolve_under_root(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RAGContractError(
            f"corpus path escapes repository root: {relative!r}"
        ) from exc
    return candidate


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
