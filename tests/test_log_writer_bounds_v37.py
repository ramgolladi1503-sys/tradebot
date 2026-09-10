import json

from core.log_writer import JsonlWriter


def test_jsonl_writer_rejects_oversized_record(tmp_path):
    writer = JsonlWriter(tmp_path / "events.jsonl", max_record_bytes=32)
    assert writer.write({"payload": "x" * 100}) is False
    assert not (tmp_path / "events.jsonl").exists()


def test_jsonl_writer_rotates_with_bounded_retention(tmp_path):
    path = tmp_path / "events.jsonl"
    writer = JsonlWriter(path, max_record_bytes=80, max_file_bytes=80, backup_count=2)
    for index in range(20):
        assert writer.write({"i": index, "payload": "x" * 20}) is True
    writer.close()
    files = sorted(tmp_path.glob("events.jsonl*"))
    assert len(files) <= 3
    assert all(file.stat().st_size <= 80 for file in files)
    assert all(json.loads(line) for file in files for line in file.read_text().splitlines())
