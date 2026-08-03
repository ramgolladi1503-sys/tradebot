"""Deterministic, local evidence retrieval for the TradeBot repository.

The module intentionally stays read-only with respect to trading runtime state. It
indexes repository text, retrieves evidence, and synthesizes citation-first answers.
It does not call a broker, mutate strategies, or make execution decisions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence

SCHEMA_VERSION = 1
DEFAULT_INCLUDE_PATHS = ("README.md", "docs", "research")
SUPPORTED_SUFFIXES = frozenset({".md", ".txt", ".json", ".yaml", ".yml"})
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".runtime",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "logs",
        "data",
        "models",
        "external_local_dirs",
    }
)
EXCLUDED_FILE_STEMS = frozenset({
    "process_memory_raw",
    "environment_raw",
    "credentials_raw",
    "secrets_raw",
    "tokens_raw",
})
DEFAULT_MAX_FILE_BYTES = 2_000_000
DEFAULT_CHUNK_CHARS = 1_800
DEFAULT_OVERLAP_LINES = 3
TOKEN_RE = re.compile(r"[A-Za-z0-9_./#:+-]{2,}")
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does",
    "for", "from", "how", "in", "into", "is", "it", "of", "on", "or", "that",
    "the", "their", "these", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "with",
})
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class SourceChunk:
    path: str
    ordinal: int
    start_line: int
    end_line: int
    section: str
    text: str
    sha256: str


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    path: str
    ordinal: int
    start_line: int
    end_line: int
    section: str
    text: str
    score: float

    @property
    def citation(self) -> str:
        return f"{self.path}:L{self.start_line}-L{self.end_line}"


@dataclass(frozen=True)
class IndexBuildReport:
    index_path: str
    scanned_files: int
    indexed_files: int
    unchanged_files: int
    removed_files: int
    chunk_count: int
    skipped_files: int
    fts_enabled: bool
    built_at_utc: str


@dataclass(frozen=True)
class GroundedAnswer:
    query: str
    answer: str
    confidence: str
    citations: tuple[str, ...]
    hits: tuple[SearchHit, ...]
    refusal_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["hits"] = [asdict(hit) | {"citation": hit.citation} for hit in self.hits]
        return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _is_allowed_file(
    path: Path,
    *,
    relative_parts: Sequence[str],
    max_file_bytes: int,
) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return False
    if path.stem.lower() in EXCLUDED_FILE_STEMS:
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in relative_parts):
        return False
    if any(part.startswith(".") for part in relative_parts):
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    return 0 < size <= max_file_bytes


def discover_source_files(
    repo_root: Path | str,
    *,
    include_paths: Sequence[str] = DEFAULT_INCLUDE_PATHS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> tuple[list[Path], int]:
    """Return deterministic, safe source files and the count of skipped candidates."""

    root = Path(repo_root).expanduser().resolve()
    discovered: dict[str, Path] = {}
    skipped = 0

    for raw_include in include_paths:
        include = (root / raw_include).resolve()
        if not _is_within(root, include):
            raise ValueError(f"include_path_outside_repo:{raw_include}")
        if not include.exists():
            skipped += 1
            continue
        candidates: Iterable[Path]
        if include.is_file():
            candidates = (include,)
        else:
            candidates = include.rglob("*")
        for path in candidates:
            if path.is_symlink():
                skipped += 1
                continue
            resolved = path.resolve()
            if not _is_within(root, resolved):
                if path.is_file():
                    skipped += 1
                continue
            relative_path = resolved.relative_to(root)
            if not _is_allowed_file(
                resolved,
                relative_parts=relative_path.parts,
                max_file_bytes=max_file_bytes,
            ):
                if path.is_file():
                    skipped += 1
                continue
            relative = relative_path.as_posix()
            discovered[relative] = resolved

    ordered = [discovered[key] for key in sorted(discovered)]
    return ordered, skipped


def _section_for_line(lines: Sequence[str], line_index: int) -> str:
    for index in range(line_index, -1, -1):
        match = MARKDOWN_HEADING_RE.match(lines[index])
        if match:
            return match.group(2).strip()[:240]
    return ""


def _split_oversized_line(line: str, *, max_chars: int) -> Iterator[str]:
    if len(line) <= max_chars:
        yield line
        return
    start = 0
    while start < len(line):
        yield line[start : start + max_chars]
        start += max_chars


def chunk_text(
    relative_path: str,
    text: str,
    *,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> list[SourceChunk]:
    """Split text into line-addressable chunks with small deterministic overlap."""

    if max_chars < 200:
        raise ValueError("max_chars_too_small")
    if overlap_lines < 0:
        raise ValueError("overlap_lines_negative")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = normalized.split("\n")
    expanded: list[tuple[int, str]] = []
    for line_number, line in enumerate(raw_lines, start=1):
        pieces = list(_split_oversized_line(line, max_chars=max_chars))
        expanded.extend((line_number, piece) for piece in pieces)

    chunks: list[SourceChunk] = []
    cursor = 0
    ordinal = 0
    while cursor < len(expanded):
        while cursor < len(expanded) and not expanded[cursor][1].strip():
            cursor += 1
        if cursor >= len(expanded):
            break

        start = cursor
        char_count = 0
        end = cursor
        while end < len(expanded):
            addition = len(expanded[end][1]) + 1
            if end > start and char_count + addition > max_chars:
                break
            char_count += addition
            end += 1

        selected = expanded[start:end]
        rendered = "\n".join(part for _, part in selected).strip()
        if rendered:
            start_line = selected[0][0]
            end_line = selected[-1][0]
            section_index = max(0, start_line - 1)
            section = _section_for_line(raw_lines, min(section_index, len(raw_lines) - 1))
            chunks.append(
                SourceChunk(
                    path=relative_path,
                    ordinal=ordinal,
                    start_line=start_line,
                    end_line=end_line,
                    section=section,
                    text=rendered,
                    sha256=_sha256_bytes(rendered.encode("utf-8")),
                )
            )
            ordinal += 1

        if end >= len(expanded):
            break
        next_cursor = max(start + 1, end - overlap_lines)
        cursor = next_cursor

    return chunks


def _connect(index_path: Path | str) -> sqlite3.Connection:
    path = Path(index_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> bool:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rag_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rag_documents (
            path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            indexed_at_utc TEXT NOT NULL,
            chunk_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rag_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL REFERENCES rag_documents(path) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            section TEXT NOT NULL,
            text TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            UNIQUE(path, ordinal)
        );

        CREATE INDEX IF NOT EXISTS idx_rag_chunks_path ON rag_chunks(path);
        """
    )
    fts_enabled = True
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts "
            "USING fts5(text, path UNINDEXED, section UNINDEXED, tokenize='porter unicode61')"
        )
        chunk_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0])
        fts_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks_fts").fetchone()[0])
        if fts_count != chunk_count:
            connection.execute("DELETE FROM rag_chunks_fts")
            connection.execute(
                "INSERT INTO rag_chunks_fts(rowid, text, path, section) "
                "SELECT id, text, path, section FROM rag_chunks"
            )
    except sqlite3.OperationalError:
        fts_enabled = False
    connection.execute(
        "INSERT INTO rag_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    connection.execute(
        "INSERT INTO rag_meta(key, value) VALUES('fts_enabled', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("1" if fts_enabled else "0",),
    )
    connection.commit()
    return fts_enabled


def _delete_document(connection: sqlite3.Connection, path: str, *, fts_enabled: bool) -> None:
    if fts_enabled:
        ids = [row[0] for row in connection.execute("SELECT id FROM rag_chunks WHERE path = ?", (path,))]
        connection.executemany("DELETE FROM rag_chunks_fts WHERE rowid = ?", ((chunk_id,) for chunk_id in ids))
    connection.execute("DELETE FROM rag_documents WHERE path = ?", (path,))


def build_index(
    repo_root: Path | str,
    index_path: Path | str,
    *,
    include_paths: Sequence[str] = DEFAULT_INCLUDE_PATHS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> IndexBuildReport:
    """Incrementally build the local TradeBot evidence index."""

    root = Path(repo_root).expanduser().resolve()
    sources, skipped_files = discover_source_files(
        root,
        include_paths=include_paths,
        max_file_bytes=max_file_bytes,
    )
    now = _utc_now()
    indexed_files = 0
    unchanged_files = 0
    removed_files = 0

    with _connect(index_path) as connection:
        fts_enabled = _ensure_schema(connection)
        existing = {
            row["path"]: row["sha256"]
            for row in connection.execute("SELECT path, sha256 FROM rag_documents")
        }
        discovered_paths: set[str] = set()

        for source in sources:
            relative = source.relative_to(root).as_posix()
            discovered_paths.add(relative)
            try:
                raw = source.read_bytes()
            except OSError:
                if relative in existing:
                    _delete_document(connection, relative, fts_enabled=fts_enabled)
                    removed_files += 1
                skipped_files += 1
                continue
            digest = _sha256_bytes(raw)
            if existing.get(relative) == digest:
                unchanged_files += 1
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                if relative in existing:
                    _delete_document(connection, relative, fts_enabled=fts_enabled)
                    removed_files += 1
                skipped_files += 1
                continue
            chunks = chunk_text(
                relative,
                text,
                max_chars=max_chunk_chars,
                overlap_lines=overlap_lines,
            )
            if not chunks:
                if relative in existing:
                    _delete_document(connection, relative, fts_enabled=fts_enabled)
                    removed_files += 1
                skipped_files += 1
                continue

            _delete_document(connection, relative, fts_enabled=fts_enabled)
            stat = source.stat()
            connection.execute(
                "INSERT INTO rag_documents(path, sha256, size_bytes, mtime_ns, indexed_at_utc, chunk_count) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (relative, digest, stat.st_size, stat.st_mtime_ns, now, len(chunks)),
            )
            for chunk in chunks:
                cursor = connection.execute(
                    "INSERT INTO rag_chunks(path, ordinal, start_line, end_line, section, text, sha256) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (
                        chunk.path,
                        chunk.ordinal,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.section,
                        chunk.text,
                        chunk.sha256,
                    ),
                )
                if fts_enabled:
                    connection.execute(
                        "INSERT INTO rag_chunks_fts(rowid, text, path, section) VALUES(?, ?, ?, ?)",
                        (cursor.lastrowid, chunk.text, chunk.path, chunk.section),
                    )
            indexed_files += 1

        for stale_path in sorted(set(existing) - discovered_paths):
            _delete_document(connection, stale_path, fts_enabled=fts_enabled)
            removed_files += 1

        chunk_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0])
        metadata = {
            "last_built_at_utc": now,
            "repo_root": str(root),
            "include_paths": json.dumps(list(include_paths), sort_keys=True),
            "chunk_count": str(chunk_count),
        }
        connection.executemany(
            "INSERT INTO rag_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            metadata.items(),
        )
        connection.commit()

    return IndexBuildReport(
        index_path=str(Path(index_path).expanduser()),
        scanned_files=len(sources),
        indexed_files=indexed_files,
        unchanged_files=unchanged_files,
        removed_files=removed_files,
        chunk_count=chunk_count,
        skipped_files=skipped_files,
        fts_enabled=fts_enabled,
        built_at_utc=now,
    )


def _query_tokens(query: str) -> list[str]:
    tokens = [
        match.group(0).lower()
        for match in TOKEN_RE.finditer(query)
        if match.group(0).lower() not in STOPWORDS
    ]
    return list(dict.fromkeys(tokens))


def _fts_expression(tokens: Sequence[str]) -> str:
    safe = [token.replace('"', '""') for token in tokens if token]
    return " OR ".join(f'"{token}"' for token in safe)


def _fetch_candidates(
    connection: sqlite3.Connection,
    query: str,
    *,
    top_k: int,
    path_prefix: str | None,
) -> list[sqlite3.Row]:
    tokens = _query_tokens(query)
    if not tokens:
        return []
    fts_row = connection.execute("SELECT value FROM rag_meta WHERE key='fts_enabled'").fetchone()
    fts_enabled = bool(fts_row and fts_row[0] == "1")
    candidate_limit = max(top_k * 10, 40)

    if fts_enabled:
        expression = _fts_expression(tokens)
        sql = (
            "SELECT c.*, bm25(rag_chunks_fts) AS raw_rank "
            "FROM rag_chunks_fts JOIN rag_chunks c ON c.id = rag_chunks_fts.rowid "
            "WHERE rag_chunks_fts MATCH ?"
        )
        params: list[object] = [expression]
        if path_prefix:
            sql += " AND c.path LIKE ?"
            params.append(path_prefix.rstrip("/") + "%")
        sql += " ORDER BY raw_rank ASC, c.path ASC, c.ordinal ASC LIMIT ?"
        params.append(candidate_limit)
        try:
            return list(connection.execute(sql, params))
        except sqlite3.OperationalError:
            pass

    clauses = []
    params = []
    for token in tokens[:12]:
        clauses.append("LOWER(text) LIKE ?")
        params.append(f"%{token}%")
    sql = "SELECT *, 0.0 AS raw_rank FROM rag_chunks WHERE (" + " OR ".join(clauses) + ")"
    if path_prefix:
        sql += " AND path LIKE ?"
        params.append(path_prefix.rstrip("/") + "%")
    sql += " ORDER BY path ASC, ordinal ASC LIMIT ?"
    params.append(candidate_limit)
    return list(connection.execute(sql, params))


def search_index(
    index_path: Path | str,
    query: str,
    *,
    top_k: int = 8,
    path_prefix: str | None = None,
) -> list[SearchHit]:
    """Retrieve and rank evidence chunks with exact-identifier and coverage boosts."""

    cleaned_query = query.strip()
    if not cleaned_query:
        return []
    if top_k < 1 or top_k > 50:
        raise ValueError("top_k_out_of_range")
    path = Path(index_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"rag_index_missing:{path}")

    query_tokens = _query_tokens(cleaned_query)
    query_token_set = set(query_tokens)
    lowered_query = cleaned_query.lower()

    with _connect(path) as connection:
        _ensure_schema(connection)
        rows = _fetch_candidates(
            connection,
            cleaned_query,
            top_k=top_k,
            path_prefix=path_prefix,
        )

    scored: list[SearchHit] = []
    candidate_count = max(1, len(rows))
    for rank_index, row in enumerate(rows):
        searchable = f"{row['path']}\n{row['section']}\n{row['text']}".lower()
        chunk_tokens = set(_query_tokens(searchable))
        coverage = len(query_token_set & chunk_tokens) / max(1, len(query_token_set))
        position_score = 1.0 - (rank_index / candidate_count)
        exact_phrase = 1.0 if lowered_query in searchable else 0.0
        identifier_tokens = [token for token in query_tokens if any(ch.isdigit() for ch in token) or token.startswith("#")]
        identifier_match = (
            sum(token in searchable for token in identifier_tokens) / len(identifier_tokens)
            if identifier_tokens
            else 0.0
        )
        path_overlap = len(query_token_set & set(_query_tokens(row["path"]))) / max(1, len(query_token_set))
        score = (
            0.45 * position_score * coverage
            + 0.40 * coverage
            + 0.08 * exact_phrase
            + 0.05 * identifier_match
            + 0.02 * path_overlap
        )
        score = max(0.0, min(1.0, score))
        scored.append(
            SearchHit(
                chunk_id=int(row["id"]),
                path=str(row["path"]),
                ordinal=int(row["ordinal"]),
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                section=str(row["section"]),
                text=str(row["text"]),
                score=round(score, 6),
            )
        )

    scored.sort(key=lambda hit: (-hit.score, hit.path, hit.ordinal))
    selected: list[SearchHit] = []
    seen_text_hashes: set[str] = set()
    for hit in scored:
        fingerprint = _sha256_bytes(re.sub(r"\s+", " ", hit.text.lower()).encode("utf-8"))
        if fingerprint in seen_text_hashes:
            continue
        seen_text_hashes.add(fingerprint)
        selected.append(hit)
        if len(selected) >= top_k:
            break
    return selected


def _best_excerpt(hit: SearchHit, query_tokens: set[str], *, max_chars: int = 420) -> str:
    candidates = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(hit.text) if segment.strip()]
    if not candidates:
        return hit.text[:max_chars].strip()

    def candidate_score(segment: str) -> tuple[float, int]:
        segment_tokens = set(_query_tokens(segment))
        overlap = len(query_tokens & segment_tokens) / max(1, len(query_tokens))
        return overlap, min(len(segment), max_chars)

    best = max(candidates, key=candidate_score)
    compact = re.sub(r"\s+", " ", best).strip()
    if len(compact) > max_chars:
        compact = compact[: max_chars - 1].rstrip() + "…"
    return compact


def _has_minimum_lexical_support(query: str, hit: SearchHit) -> bool:
    query_tokens = set(_query_tokens(query))
    if not query_tokens:
        return False
    searchable_tokens = set(_query_tokens(f"{hit.path}\n{hit.section}\n{hit.text}"))
    overlap_count = len(query_tokens & searchable_tokens)
    if len(query_tokens) == 1:
        return overlap_count == 1
    if overlap_count < 2:
        return False
    if len(query_tokens) >= 4:
        return overlap_count / len(query_tokens) >= 0.30
    return True


def synthesize_answer(
    query: str,
    hits: Sequence[SearchHit],
    *,
    min_score: float = 0.28,
    max_evidence: int = 5,
) -> GroundedAnswer:
    """Create an extractive answer that cannot introduce unsupported facts."""

    usable = [
        hit
        for hit in hits
        if hit.score >= min_score and _has_minimum_lexical_support(query, hit)
    ]
    if not usable:
        return GroundedAnswer(
            query=query,
            answer=(
                "I could not find sufficiently strong evidence in the indexed TradeBot sources. "
                "Rephrase the question or rebuild the index after adding the relevant document."
            ),
            confidence="insufficient_evidence",
            citations=(),
            hits=tuple(hits),
            refusal_reason="retrieval_below_minimum_score",
        )

    query_tokens = set(_query_tokens(query))
    selected = usable[:max_evidence]
    lines = ["The indexed TradeBot evidence supports these points:"]
    citations: list[str] = []
    for hit in selected:
        excerpt = _best_excerpt(hit, query_tokens)
        citation = hit.citation
        citations.append(citation)
        section = f" — {hit.section}" if hit.section else ""
        lines.append(f"- {excerpt} [{citation}]{section}")

    top_score = selected[0].score
    source_count = len({hit.path for hit in selected})
    if top_score >= 0.72 and source_count >= 2:
        confidence = "high"
    elif top_score >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    return GroundedAnswer(
        query=query,
        answer="\n".join(lines),
        confidence=confidence,
        citations=tuple(dict.fromkeys(citations)),
        hits=tuple(hits),
    )


def ask_index(
    index_path: Path | str,
    query: str,
    *,
    top_k: int = 8,
    path_prefix: str | None = None,
    min_score: float = 0.28,
) -> GroundedAnswer:
    hits = search_index(index_path, query, top_k=top_k, path_prefix=path_prefix)
    return synthesize_answer(query, hits, min_score=min_score)


def index_status(index_path: Path | str) -> dict[str, object]:
    path = Path(index_path).expanduser()
    if not path.exists():
        return {"exists": False, "index_path": str(path)}
    with _connect(path) as connection:
        _ensure_schema(connection)
        metadata = {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM rag_meta")}
        document_count = int(connection.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0])
        chunk_count = int(connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0])
    return {
        "exists": True,
        "index_path": str(path),
        "document_count": document_count,
        "chunk_count": chunk_count,
        "schema_version": int(metadata.get("schema_version", "0")),
        "fts_enabled": metadata.get("fts_enabled") == "1",
        "last_built_at_utc": metadata.get("last_built_at_utc"),
        "include_paths": json.loads(metadata.get("include_paths", "[]")),
    }


def default_index_path(repo_root: Path | str) -> Path:
    override = os.getenv("TRADEBOT_RAG_INDEX", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(repo_root).expanduser().resolve() / ".runtime" / "rag" / "tradebot_rag.sqlite"


__all__ = [
    "DEFAULT_INCLUDE_PATHS",
    "GroundedAnswer",
    "IndexBuildReport",
    "SearchHit",
    "SourceChunk",
    "ask_index",
    "build_index",
    "chunk_text",
    "default_index_path",
    "discover_source_files",
    "index_status",
    "search_index",
    "synthesize_answer",
]
