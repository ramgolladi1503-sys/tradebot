from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import PurePosixPath
from typing import Any


_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")


class RAGContractError(ValueError):
    """Raised when governed corpus metadata is invalid."""


class SourceType(str, Enum):
    CERTIFICATION_POLICY = "certification_policy"
    EXECUTABLE_CONTRACT = "executable_contract"
    STRATEGY_CONTRACT = "strategy_contract"
    TEST_EVIDENCE = "test_evidence"
    AUDIT_REPORT = "audit_report"
    RUNBOOK = "runbook"
    HISTORICAL_REPORT = "historical_report"
    AGENT_GENERATED = "agent_generated"


class AuthorityClass(str, Enum):
    CANONICAL = "canonical"
    EXECUTABLE = "executable"
    TESTED = "tested"
    COMMITTED_AUDIT = "committed_audit"
    RUNBOOK = "runbook"
    HISTORICAL = "historical"
    AGENT_GENERATED = "agent_generated"

    @property
    def rank(self) -> int:
        return {
            AuthorityClass.CANONICAL: 100,
            AuthorityClass.EXECUTABLE: 90,
            AuthorityClass.TESTED: 80,
            AuthorityClass.COMMITTED_AUDIT: 70,
            AuthorityClass.RUNBOOK: 60,
            AuthorityClass.HISTORICAL: 30,
            AuthorityClass.AGENT_GENERATED: 10,
        }[self]


_ALLOWED_AUTHORITY_BY_SOURCE_TYPE: dict[SourceType, frozenset[AuthorityClass]] = {
    SourceType.CERTIFICATION_POLICY: frozenset({AuthorityClass.CANONICAL}),
    SourceType.EXECUTABLE_CONTRACT: frozenset(
        {AuthorityClass.CANONICAL, AuthorityClass.EXECUTABLE}
    ),
    SourceType.STRATEGY_CONTRACT: frozenset(
        {AuthorityClass.CANONICAL, AuthorityClass.EXECUTABLE}
    ),
    SourceType.TEST_EVIDENCE: frozenset({AuthorityClass.TESTED}),
    SourceType.AUDIT_REPORT: frozenset({AuthorityClass.COMMITTED_AUDIT}),
    SourceType.RUNBOOK: frozenset({AuthorityClass.RUNBOOK}),
    SourceType.HISTORICAL_REPORT: frozenset({AuthorityClass.HISTORICAL}),
    SourceType.AGENT_GENERATED: frozenset({AuthorityClass.AGENT_GENERATED}),
}


@dataclass(frozen=True)
class CorpusSourceSpec:
    source_id: str
    path: str
    source_type: SourceType
    authority: AuthorityClass
    version: str
    effective_from: date
    effective_until: date | None = None
    superseded_by: str | None = None
    module: str | None = None
    strategy_id: str | None = None

    def __post_init__(self) -> None:
        _validate_source_id(self.source_id)
        _validate_relative_path(self.path)
        if not _VERSION_RE.fullmatch(self.version):
            raise RAGContractError(
                f"source {self.source_id} has invalid version {self.version!r}"
            )
        if self.authority not in _ALLOWED_AUTHORITY_BY_SOURCE_TYPE[self.source_type]:
            raise RAGContractError(
                f"source {self.source_id} cannot use authority {self.authority.value} "
                f"for type {self.source_type.value}"
            )
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise RAGContractError(
                f"source {self.source_id} effective_until precedes effective_from"
            )
        if self.superseded_by is not None:
            _validate_source_id(self.superseded_by)
            if self.superseded_by == self.source_id:
                raise RAGContractError(f"source {self.source_id} cannot supersede itself")
            if self.effective_until is None:
                raise RAGContractError(
                    f"source {self.source_id} requires effective_until when superseded"
                )
        if self.strategy_id is not None and not self.strategy_id.strip():
            raise RAGContractError("strategy_id cannot be blank")
        if self.module is not None and not self.module.strip():
            raise RAGContractError("module cannot be blank")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "path": self.path,
            "source_type": self.source_type.value,
            "authority": self.authority.value,
            "authority_rank": self.authority.rank,
            "version": self.version,
            "effective_from": self.effective_from.isoformat(),
            "effective_until": (
                self.effective_until.isoformat()
                if self.effective_until is not None
                else None
            ),
            "superseded_by": self.superseded_by,
            "module": self.module,
            "strategy_id": self.strategy_id,
        }


@dataclass(frozen=True)
class CorpusSourceRecord:
    spec: CorpusSourceSpec
    repository_commit: str
    content_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not _COMMIT_RE.fullmatch(self.repository_commit):
            raise RAGContractError(
                f"source {self.spec.source_id} has invalid repository commit"
            )
        if not _SHA256_RE.fullmatch(self.content_sha256):
            raise RAGContractError(
                f"source {self.spec.source_id} has invalid content SHA-256"
            )
        if self.size_bytes <= 0:
            raise RAGContractError(
                f"source {self.spec.source_id} must contain non-empty content"
            )

    @property
    def source_id(self) -> str:
        return self.spec.source_id

    @property
    def path(self) -> str:
        return self.spec.path

    @property
    def authority_rank(self) -> int:
        return self.spec.authority.rank

    def is_effective(self, on_date: date) -> bool:
        if on_date < self.spec.effective_from:
            return False
        if self.spec.effective_until is not None and on_date > self.spec.effective_until:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.spec.to_dict(),
            "repository_commit": self.repository_commit,
            "content_sha256": self.content_sha256,
            "size_bytes": self.size_bytes,
        }


def source_spec_from_dict(payload: dict[str, Any]) -> CorpusSourceSpec:
    try:
        source_type = SourceType(str(payload["source_type"]))
        authority = AuthorityClass(str(payload["authority"]))
        effective_from = date.fromisoformat(str(payload["effective_from"]))
        effective_until = (
            date.fromisoformat(str(payload["effective_until"]))
            if payload.get("effective_until")
            else None
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RAGContractError(f"invalid corpus source metadata: {exc}") from exc
    return CorpusSourceSpec(
        source_id=str(payload.get("source_id") or ""),
        path=str(payload.get("path") or ""),
        source_type=source_type,
        authority=authority,
        version=str(payload.get("version") or ""),
        effective_from=effective_from,
        effective_until=effective_until,
        superseded_by=(
            str(payload["superseded_by"])
            if payload.get("superseded_by")
            else None
        ),
        module=str(payload["module"]) if payload.get("module") else None,
        strategy_id=(
            str(payload["strategy_id"])
            if payload.get("strategy_id")
            else None
        ),
    )


def _validate_source_id(value: str) -> None:
    if not _SOURCE_ID_RE.fullmatch(value):
        raise RAGContractError(f"invalid corpus source id: {value!r}")


def _validate_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
    ):
        raise RAGContractError(f"unsafe corpus source path: {value!r}")
    if path.suffix.lower() not in {".md", ".json", ".jsonl"}:
        raise RAGContractError(
            f"unsupported corpus source extension: {path.suffix!r}"
        )
