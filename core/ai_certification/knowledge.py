from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    heading: str
    text: str
    authority: int

    @property
    def citation(self) -> str:
        return f"{self.source}#{self.heading}" if self.heading else self.source


class CuratedKnowledgeBase:
    """Small authority-ranked corpus; it never indexes arbitrary runtime files."""

    def __init__(self, chunks: Iterable[KnowledgeChunk] = ()) -> None:
        self._chunks = tuple(chunks)

    @classmethod
    def from_repository(cls, repository_root: str | Path) -> "CuratedKnowledgeBase":
        root = Path(repository_root).resolve()
        sources = (
            ("docs/ai_certification/certification_policy_v1.md", 100),
            ("docs/ai_certification/mvp_scope.md", 90),
            ("docs/research/strategy_backtesting_engine_audit.md", 80),
        )
        chunks: list[KnowledgeChunk] = []
        for relative, authority in sources:
            path = (root / relative).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                continue
            if not path.is_file():
                continue
            chunks.extend(_chunk_markdown(relative, path.read_text(encoding="utf-8"), authority))
        return cls(chunks)

    def retrieve(self, query: str, *, limit: int = 4) -> tuple[KnowledgeChunk, ...]:
        query_tokens = _tokens(query)
        scored: list[tuple[int, int, str, KnowledgeChunk]] = []
        for chunk in self._chunks:
            overlap = len(query_tokens & _tokens(f"{chunk.heading} {chunk.text}"))
            if overlap == 0:
                continue
            scored.append((overlap, chunk.authority, chunk.citation, chunk))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return tuple(item[3] for item in scored[: max(0, limit)])


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(value)}


def _chunk_markdown(source: str, text: str, authority: int) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    heading = ""
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if body:
                chunks.append(KnowledgeChunk(source, heading, "\n".join(body).strip(), authority))
                body = []
            heading = line.lstrip("#").strip()
        else:
            body.append(line)
    if body:
        chunks.append(KnowledgeChunk(source, heading, "\n".join(body).strip(), authority))
    return [chunk for chunk in chunks if chunk.text]
