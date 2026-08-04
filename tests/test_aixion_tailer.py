from __future__ import annotations

import json
import pytest
from aixion_trade_intelligence.tailer import JsonlTailer, TailerError


def test_tailer_checkpoints_complete_lines(tmp_path):
    source = tmp_path / "source.jsonl"; checkpoint = tmp_path / "checkpoint.json"; source.write_bytes(b'{"a":1}\n{"b":2}'); tailer = JsonlTailer(source, checkpoint)
    assert [record.row for record in tailer.read_available()] == [{"a": 1}]
    with source.open("ab") as handle: handle.write(b"\n")
    assert [record.row for record in tailer.read_available()] == [{"b": 2}]; assert tailer.read_available() == ()


def test_tailer_resets_after_truncation(tmp_path):
    source = tmp_path / "source.jsonl"; checkpoint = tmp_path / "checkpoint.json"; source.write_text('{"a":1}\n', encoding="utf-8"); tailer = JsonlTailer(source, checkpoint); assert len(tailer.read_available()) == 1
    source.write_text('{"c":3}\n', encoding="utf-8"); assert [record.row for record in tailer.read_available()] == [{"c": 3}]


def test_tailer_does_not_advance_past_bad_json(tmp_path):
    source = tmp_path / "source.jsonl"; checkpoint = tmp_path / "checkpoint.json"; source.write_text('{"a":1}\nnot-json\n', encoding="utf-8"); tailer = JsonlTailer(source, checkpoint)
    with pytest.raises(TailerError, match="invalid JSONL"): tailer.read_available()
    assert json.loads(checkpoint.read_text())["offset"] < source.stat().st_size if checkpoint.exists() else True
