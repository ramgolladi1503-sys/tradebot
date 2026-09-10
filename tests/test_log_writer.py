from pathlib import Path

from core.log_writer import get_jsonl_writer


def test_log_writer_appends_jsonl(tmp_path: Path):
    path = tmp_path / "test.jsonl"
    writer = get_jsonl_writer(path)
    assert writer.write({"event": "one"})
    assert writer.write({"event": "two"})
    content = path.read_text().strip().splitlines()
    import json
    assert len(content) == 2
    assert json.loads(content[0]) == {"event": "one"}
    assert json.loads(content[1]) == {"event": "two"}
