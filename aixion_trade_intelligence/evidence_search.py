from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_TOKEN = re.compile(r"[A-Za-z0-9_\-]+")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text)}


@dataclass(frozen=True)
class EvidenceDocument:
    document_id: str
    document_type: str
    source_path: str
    content: str
    metadata: dict[str, str]


class EvidenceIndex:
    """Small-corpus metadata and keyword evidence index.

    Numeric facts remain in structured session artifacts. This index exists for
    exact document retrieval and historical explanation; it does not embed raw
    market ticks or calculate analytics.
    """

    def __init__(self, documents: Iterable[EvidenceDocument]) -> None:
        self.documents = tuple(documents)
        ids = [document.document_id for document in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_document_id")
        self._terms = {
            document.document_id: _tokens(
                " ".join(
                    [
                        document.document_type,
                        document.source_path,
                        document.content,
                        " ".join(f"{key} {value}" for key, value in document.metadata.items()),
                    ]
                )
            )
            for document in self.documents
        }

    @classmethod
    def from_paths(cls, paths: Iterable[str | Path]) -> "EvidenceIndex":
        documents: list[EvidenceDocument] = []
        for raw_path in paths:
            path = Path(raw_path)
            content = path.read_text(encoding="utf-8")
            metadata: dict[str, str] = {}
            document_type = path.suffix.lower().lstrip(".") or "text"
            if path.suffix.lower() == ".json":
                payload = json.loads(content)
                if isinstance(payload, dict):
                    for key in (
                        "study_id",
                        "session_id",
                        "strategy_id",
                        "verdict",
                        "data_quality_state",
                    ):
                        value = payload.get(key)
                        if value is not None and not isinstance(value, (dict, list)):
                            metadata[key] = str(value)
            document_id = path.as_posix()
            documents.append(
                EvidenceDocument(
                    document_id=document_id,
                    document_type=document_type,
                    source_path=path.as_posix(),
                    content=content,
                    metadata=metadata,
                )
            )
        return cls(documents)

    def search(
        self,
        query: str,
        *,
        metadata_filters: dict[str, str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        if limit <= 0:
            raise ValueError("limit_must_be_positive")
        query_terms = _tokens(query)
        if not query_terms:
            raise ValueError("empty_query")
        filters = {str(key): str(value) for key, value in (metadata_filters or {}).items()}
        ranked: list[tuple[float, EvidenceDocument, list[str]]] = []
        for document in self.documents:
            if any(document.metadata.get(key) != value for key, value in filters.items()):
                continue
            terms = self._terms[document.document_id]
            matched = sorted(query_terms & terms)
            if not matched:
                continue
            coverage = len(matched) / len(query_terms)
            specificity = len(matched) / max(len(terms), 1)
            score = coverage + specificity
            ranked.append((score, document, matched))
        ranked.sort(key=lambda item: (-item[0], item[1].document_id))
        return [
            {
                "document_id": document.document_id,
                "document_type": document.document_type,
                "source_path": document.source_path,
                "metadata": dict(document.metadata),
                "score": score,
                "matched_terms": matched,
            }
            for score, document, matched in ranked[:limit]
        ]
