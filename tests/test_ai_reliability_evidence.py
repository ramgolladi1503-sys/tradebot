import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.ai_reliability_agent.evidence import EvidenceLedger, canonical_json, redact


@pytest.mark.parametrize(
    "key",
    [
        "access_token", "api_key", "apikey", "authorization", "client_secret", "password",
        "refresh_token", "secret", "session_token", "openai_api_key", "nested_token_value",
    ],
)
def test_redacts_sensitive_keys(key):
    assert redact({key: "value"})[key] == "[REDACTED]"


@pytest.mark.parametrize(
    "value",
    [
        "sk-abcdefghijklmnopqrstuvwxyz123456",
        "Bearer abcdefghijklmnopqrstuvwxyz.123456",
    ],
)
def test_redacts_secret_value_patterns(value):
    assert "[REDACTED]" in redact({"message": value})["message"]


def test_redact_preserves_safe_nested_values():
    assert redact({"a": [{"b": 2}]}) == {"a": [{"b": 2}]}


def test_canonical_json_stable_order():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_empty_ledger_is_valid(tmp_path):
    verification = EvidenceLedger(tmp_path / "evidence.jsonl").verify()
    assert verification.valid is True
    assert verification.row_count == 0


def test_append_and_get_payload(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("test", {"x": 1}, session_id="S1")
    assert ledger.payload(ref.evidence_id) == {"x": 1}
    assert ledger.verify().valid is True


def test_chain_links_rows(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    one = ledger.append("one", {"x": 1}, session_id="S1")
    two = ledger.append("two", {"x": 2}, session_id="S1")
    rows = ledger.rows()
    assert rows[1]["previous_sha256"] == one.sha256
    assert two.sha256 == rows[1]["sha256"]


def test_tamper_is_detected(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(path)
    ledger.append("one", {"x": 1}, session_id="S1")
    row = json.loads(path.read_text())
    row["payload"]["x"] = 999
    path.write_text(json.dumps(row) + "\n")
    verification = ledger.verify()
    assert verification.valid is False
    assert "sha256_mismatch" in verification.errors[0]


def test_broken_previous_hash_is_detected(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(path)
    ledger.append("one", {"x": 1}, session_id="S1")
    ledger.append("two", {"x": 2}, session_id="S1")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]["previous_sha256"] = "wrong"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    assert any("previous_sha256_mismatch" in error for error in ledger.verify().errors)


def test_invalid_json_is_detected(tmp_path):
    path = tmp_path / "evidence.jsonl"
    path.write_text("not-json\n")
    verification = EvidenceLedger(path).verify()
    assert verification.valid is False
    assert verification.errors == ("row_0:invalid_json",)


def test_require_reports_missing_ids(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("one", {}, session_id="S1")
    ok, missing = ledger.require([ref.evidence_id, "missing"])
    assert ok is False
    assert missing == ("missing",)


def test_append_redacts_before_storage(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("one", {"api_key": "abc"}, session_id="S1")
    assert ledger.payload(ref.evidence_id)["api_key"] == "[REDACTED]"
    assert ledger.verify().valid is True


def test_concurrent_appends_preserve_chain(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda i: ledger.append("event", {"i": i}, session_id="S1"), range(40)))
    verification = ledger.verify()
    assert verification.valid is True
    assert verification.row_count == 40
