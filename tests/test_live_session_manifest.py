import json

import pytest

from core.live_session_manifest import LiveSessionManifest, load_session_manifest, write_session_manifest
from core.live_sidecar_contract import SidecarSpec, classify_touches, sidecar_health


def _manifest():
    return LiveSessionManifest(
        session_date="2026-08-24", session_id="s1", source_sha="a" * 40,
        observer_sha="b" * 40, observer_pid=7, runtime_root="/external/live/s1",
        sqlite_path="/external/live/s1/live.sqlite", instrument_master_path="/external/master.json",
        instrument_master_sha="c" * 64, auth_state="PASS", feed_state="PENDING",
        persistence_state="PENDING", subscription_count=None, consumer_registry=("regime", "cas_v2"),
    )


def test_manifest_is_atomic_and_execution_disabled(tmp_path):
    path = tmp_path / "SESSION_MANIFEST.json"
    digest = write_session_manifest(path, _manifest())
    payload = load_session_manifest(path)
    assert len(digest) == 64
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    assert payload["consumer_registry"] == ["cas_v2", "regime"]


def test_manifest_rejects_authority_promotion(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"session_id": "s", "source_sha": "a", "order_authority": True}))
    with pytest.raises(ValueError, match="authority"):
        load_session_manifest(path)


def test_sidecar_runtime_touch_is_not_safe():
    assert classify_touches(["core/feed/runtime_store.py"]) == "RUNTIME_CANDIDATE_REQUIRED"
    assert classify_touches(["core/analytics/report.py"]) == "SIDECAR_SAFE"


def test_sidecar_failure_is_isolated_and_read_only():
    spec = SidecarSpec(1, "a" * 40, "b" * 40, "observe", "SESSION_MANIFEST", "/evidence/1", ("core/analytics/report.py",))
    health = sidecar_health(spec, main_session_id="s1", failed=True)
    assert health["STATUS"] == "FAILED_ISOLATED"
    assert health["CAN_MUTATE_MAIN"] is False
    assert health["BROKER_WRITE_AUTHORITY"] is False
