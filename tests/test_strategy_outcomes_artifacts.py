import json

from research.strategy_outcomes.artifacts import write_json_artifact


def test_write_json_artifact_returns_hash(tmp_path):
    target = tmp_path / "artifact.json"
    payload = {"b": 1, "a": {"z": 2}}
    digest = write_json_artifact(target, payload)
    repeat_digest = write_json_artifact(tmp_path / "artifact_repeat.json", {"a": {"z": 2}, "b": 1})
    assert digest != "not_a_digest"
    assert digest == repeat_digest
    assert target.read_text().splitlines()[1].startswith('  "a"')
    assert json.loads(target.read_text()) == payload
