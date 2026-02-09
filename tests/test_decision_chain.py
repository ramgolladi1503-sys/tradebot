import json
from pathlib import Path

from core import decision_logger as dl


def _write_line(path: Path, event: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(dl._canonical_json(event) + "\n")


def test_chain_with_legacy_prefix(tmp_path: Path):
    path = tmp_path / "decision_events.jsonl"
    _write_line(path, {"trade_id": "legacy-1", "symbol": "NIFTY"})
    prev = dl.DECISION_CHAIN_GENESIS
    e1 = {"trade_id": "t1", "symbol": "NIFTY", "prev_hash": prev}
    e1["event_hash"] = dl._compute_event_hash(e1)
    _write_line(path, e1)
    ok, status, count = dl.verify_decision_chain(path)
    assert ok is True
    assert status == e1["event_hash"]
    assert count == 1


def test_chain_detects_tamper(tmp_path: Path):
    path = tmp_path / "decision_events.jsonl"
    prev = dl.DECISION_CHAIN_GENESIS
    e1 = {"trade_id": "t1", "symbol": "NIFTY", "prev_hash": prev}
    e1["event_hash"] = dl._compute_event_hash(e1)
    _write_line(path, e1)
    e2 = {"trade_id": "t2", "symbol": "SENSEX", "prev_hash": e1["event_hash"]}
    e2["event_hash"] = dl._compute_event_hash(e2)
    _write_line(path, e2)
    # Tamper with last line
    lines = path.read_text().splitlines()
    bad = json.loads(lines[-1])
    bad["symbol"] = "TAMPER"
    lines[-1] = json.dumps(bad)
    path.write_text("\n".join(lines) + "\n")
    ok, status, _ = dl.verify_decision_chain(path)
    assert ok is False
    assert status in {"event_hash_mismatch", "prev_hash_mismatch"}
