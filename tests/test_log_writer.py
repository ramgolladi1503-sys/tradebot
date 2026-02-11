from pathlib import Path

from core.log_writer import get_jsonl_writer


def test_log_writer_appends_jsonl(tmp_path: Path):
    path = tmp_path / "test.jsonl"
    writer = get_jsonl_writer(path)
    assert writer.write({"event": "one"})
    assert writer.write({"event": "two"})
    content = path.read_text().strip().splitlines()
    assert len(content) == 2
    assert "\"event\": \"one\"" in content[0]
    assert "\"event\": \"two\"" in content[1]
