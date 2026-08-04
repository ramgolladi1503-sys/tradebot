from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class EvidenceChunk:
    document_id: str
    chunk_id: str
    source_path: str
    document_type: str
    content: str
    content_hash: str
    metadata: dict[str, object]

    def to_record(self) -> dict[str, object]:
        return {"document_id": self.document_id, "chunk_id": self.chunk_id, "source_path": self.source_path, "document_type": self.document_type, "content": self.content, "content_hash": self.content_hash, "metadata": dict(self.metadata)}


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    title = "document"
    body: list[str] = []
    for line in lines:
        if line.startswith("#"):
            if body:
                sections.append((title, body))
            title = line.lstrip("#").strip() or "section"
            body = []
        else:
            body.append(line)
    if body or not sections:
        sections.append((title, body))
    return [(heading, "\n".join(rows).strip()) for heading, rows in sections if "\n".join(rows).strip()]


def ingest_evidence_file(path: str | Path, *, document_type: str, metadata: Mapping[str, object] | None = None, max_characters_per_chunk: int) -> list[EvidenceChunk]:
    source = Path(path)
    if max_characters_per_chunk <= 0:
        raise ValueError("max_characters_per_chunk_nonpositive")
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)
    raw = source.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError("evidence_file_empty")
    base_metadata = dict(metadata or {})
    base_metadata.setdefault("source_path", source.as_posix())
    base_metadata.setdefault("document_type", document_type)
    document_id = _hash_text(source.as_posix() + "\n" + raw)
    suffix = source.suffix.lower()
    if suffix == ".json":
        payload = json.loads(raw)
        sections = [("json", json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))]
        if isinstance(payload, Mapping):
            for key in ("session_id", "strategy_id", "strategy_version", "verdict", "trade_date"):
                if key in payload and key not in base_metadata:
                    base_metadata[key] = payload[key]
            manifest = payload.get("manifest")
            if isinstance(manifest, Mapping):
                for key in ("session_id", "verdict", "valid"):
                    if key in manifest and key not in base_metadata:
                        base_metadata[key] = manifest[key]
    else:
        sections = _markdown_sections(raw)
    chunks: list[EvidenceChunk] = []
    chunk_number = 0
    for heading, content in sections:
        start = 0
        while start < len(content):
            end = min(start + max_characters_per_chunk, len(content))
            if end < len(content):
                whitespace = content.rfind(" ", start, end)
                if whitespace > start:
                    end = whitespace
            piece = content[start:end].strip()
            if piece:
                chunk_number += 1
                chunk_id = f"{document_id}:{chunk_number}"
                chunks.append(EvidenceChunk(document_id, chunk_id, source.as_posix(), document_type, f"{heading}\n{piece}", _hash_text(piece), {**base_metadata, "heading": heading, "chunk_number": chunk_number}))
            start = max(end, start + 1)
    return chunks


def ingest_evidence_paths(paths: Iterable[str | Path], *, document_type_by_suffix: Mapping[str, str], max_characters_per_chunk: int) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    seen_chunk_ids: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        document_type = document_type_by_suffix.get(path.suffix.lower())
        if document_type is None:
            continue
        for chunk in ingest_evidence_file(path, document_type=document_type, max_characters_per_chunk=max_characters_per_chunk):
            if chunk.chunk_id not in seen_chunk_ids:
                chunks.append(chunk)
                seen_chunk_ids.add(chunk.chunk_id)
    return chunks


_NUMERIC_QUERY_PATTERN = re.compile(r"\b(count|average|mean|median|pnl|profit|loss|drawdown|latency|spread|return|rate|percentage|how many)\b", re.IGNORECASE)


def plan_evidence_query(question: str) -> str:
    text = question.strip()
    if not text:
        raise ValueError("evidence_question_empty")
    return "STRUCTURED_ANALYTICS" if _NUMERIC_QUERY_PATTERN.search(text) else "HYBRID_RAG"
