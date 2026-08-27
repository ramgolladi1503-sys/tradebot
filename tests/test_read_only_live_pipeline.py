import json
from datetime import date

import pytest

from core.read_only_live_pipeline import PIPELINE_STAGES, prepare_current_session


class FakeKite:
    def profile(self):
        return {"user_id": "redacted"}

    def margins(self):
        return {"available": 0}

    def instruments(self, exchange):
        return [
            {"exchange": exchange, "name": "NIFTY", "tradingsymbol": "NIFTY"},
            {"exchange": exchange, "name": "BANKNIFTY", "tradingsymbol": "BANKNIFTY"},
        ]


def test_prepare_current_session_writes_single_authority(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADEBOT_COMMIT_SHA", "a" * 40)
    monkeypatch.setattr("core.auth.get_kite_client", lambda **_: FakeKite())
    token = tmp_path / "token"
    token.write_text("opaque", encoding="utf-8")
    token.chmod(0o600)
    run_root = tmp_path / "run"
    raw = run_root / "instruments.raw.json"
    raw.parent.mkdir()
    raw.write_text("[]", encoding="utf-8")
    (run_root / "instrument_authority_manifest.json").write_text(json.dumps({
        "session_date": date.today().isoformat(), "source_sha": "a" * 40,
        "verdict": "PASS", "raw_instrument_path": str(raw),
        "raw_instrument_sha256": "b" * 64,
    }), encoding="utf-8")
    plan = prepare_current_session(
        session_date=date.today().isoformat(), runtime_root=run_root,
        token_path=token, subscription_tokens=[3, 2, 3],
    )
    manifest = json.loads((tmp_path / "run" / "SESSION_MANIFEST.json").read_text())
    assert plan["final_union_tokens"] == [2, 3]
    assert manifest["pipeline_sha"] == "a" * 40
    assert manifest["consumer_registry_path"].endswith("CONSUMERS.json")
    assert manifest["advisory_queue_path"].endswith("advisory_queue.jsonl")
    assert all(manifest[name] is False for name in (
        "broker_write_authority", "order_authority", "paper_authorized", "live_authorized",
    ))
    stages = json.loads((tmp_path / "run" / "pipeline_stage_state.json").read_text())
    assert stages["current_stage"] == "AUTH_READY"
    assert stages["pipeline_stages"] == list(PIPELINE_STAGES)
    assert stages["e2e_ready"] is False


def test_prepare_rejects_non_current_session(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADEBOT_COMMIT_SHA", "a" * 40)
    token = tmp_path / "token"
    token.write_text("opaque", encoding="utf-8")
    token.chmod(0o600)
    with pytest.raises(RuntimeError, match="NOT_CURRENT"):
        prepare_current_session(
            session_date="1900-01-01", runtime_root=tmp_path / "run",
            token_path=token, subscription_tokens=[1],
        )
