from __future__ import annotations

from pathlib import Path

from config import config as cfg
from core.runtime_snapshot_producer import _tail_jsonl_rows


def test_tail_jsonl_rows_reads_only_bounded_tail(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    rows = [f'{{"row": {i}}}' for i in range(10)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    monkeypatch.setattr(cfg, "RUNTIME_SNAPSHOT_JSONL_TAIL_BYTES", 16, raising=False)

    tail = _tail_jsonl_rows(path, limit=3)

    assert tail == rows[-3:]


def test_tail_jsonl_rows_handles_missing_file():
    assert _tail_jsonl_rows(Path("/tmp/does-not-exist.jsonl"), limit=3) == []
