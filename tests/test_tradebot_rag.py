from __future__ import annotations

from pathlib import Path

import pytest

from core.tradebot_rag import (
    ask_index,
    build_index,
    chunk_text,
    discover_source_files,
    index_status,
    search_index,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discovery_is_allowlisted_and_skips_secrets(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Safe\nEvidence")
    _write(tmp_path / "docs" / "report.md", "# Report\nAccepted")
    _write(tmp_path / "docs" / ".env", "TOKEN=secret")
    _write(tmp_path / "logs" / "runtime.md", "must not index")
    _write(tmp_path / "docs" / "binary.bin", "not supported")

    files, skipped = discover_source_files(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in files] == [
        "README.md",
        "docs/report.md",
    ]
    assert skipped >= 2


def test_chunking_preserves_line_ranges_and_overlap() -> None:
    text = "# Heading\n" + "\n".join(f"line {index} evidence" for index in range(1, 30))
    chunks = chunk_text("docs/example.md", text, max_chars=220, overlap_lines=2)

    assert len(chunks) >= 2
    assert chunks[0].start_line == 1
    assert chunks[0].end_line >= chunks[1].start_line
    assert all(chunk.section == "Heading" for chunk in chunks)
    assert all(chunk.start_line <= chunk.end_line for chunk in chunks)


def test_build_query_and_citation(tmp_path: Path) -> None:
    _write(
        tmp_path / "README.md",
        "# TradeBot\nA change must explain executable, queue-only, advisory-only, or blocked states.\n",
    )
    _write(
        tmp_path / "docs" / "strategy.md",
        "# Strategy verdict\nThe ORB hypothesis was rejected after negative walk-forward evidence.\n",
    )
    index = tmp_path / ".runtime" / "rag.sqlite"

    report = build_index(tmp_path, index)
    answer = ask_index(index, "Why was the ORB hypothesis rejected?", top_k=5, min_score=0.1)

    assert report.indexed_files == 2
    assert answer.refusal_reason is None
    assert any(citation.startswith("docs/strategy.md:L") for citation in answer.citations)
    assert "walk-forward" in answer.answer


def test_incremental_build_updates_and_removes_documents(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    report = tmp_path / "docs" / "report.md"
    _write(readme, "# TradeBot\nAlpha evidence")
    _write(report, "# Report\nBeta evidence")
    index = tmp_path / ".runtime" / "rag.sqlite"

    first = build_index(tmp_path, index)
    second = build_index(tmp_path, index)
    report.unlink()
    _write(readme, "# TradeBot\nGamma evidence")
    third = build_index(tmp_path, index)

    assert first.indexed_files == 2
    assert second.unchanged_files == 2
    assert third.indexed_files == 1
    assert third.removed_files == 1
    assert index_status(index)["document_count"] == 1
    assert search_index(index, "Gamma", top_k=3)
    assert not search_index(index, "Beta", top_k=3)


def test_no_answer_when_retrieval_has_no_support(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# TradeBot\nOnly feed freshness evidence is documented.")
    index = tmp_path / ".runtime" / "rag.sqlite"
    build_index(tmp_path, index)

    answer = ask_index(index, "What is the capital of Peru?", top_k=3)

    assert answer.refusal_reason == "retrieval_below_minimum_score"
    assert answer.citations == ()


def test_rejects_include_path_outside_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="include_path_outside_repo"):
        discover_source_files(tmp_path, include_paths=("../outside",))
